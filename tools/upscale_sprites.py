"""4x upscaled variants of the original's sprites for play mode (docs/play/hires.md).

    python3 tools/upscale_sprites.py [--models DIR] [--methods M,M] [--set NAME SPEC... ] ...

Without --set it builds the two test sets:
    walker   the immigrant (SprMain walk 8 dirs x 12 frames + die), the most common person in the city
    terrain  the plain ground and grass tiles (Zeus_Terrain SPR_IN_FILL1/2, SPR_GRASS, SPR_MEADOW*, ...)
SPEC: FILE:A-B (atlas index range), FILE@GROUP (an atlas group), walker:ROLE (its blocks in
data/play/walkers.json). Options per set go before its specs: --alpha nearest|scale4x, --context N.

Methods: nearest, scale4x (Scale2x/EPX twice, exact colour compare) and four ESRGAN models loaded with
spandrel (4x-UltraSharp, Remacri, NMKD-Siax, NMKD-Superscale). --models DIR holds the .pth weights and a
venv with spandrel + torch (DIR/venv); without spandrel in this python the tool re-runs itself there.

Per sprite:
  * shadow pixels (pure red) become black at 50% alpha, as tools/play_atlas.py does;
  * the colour goes to the model with transparent pixels filled from their neighbours ("bleed"), so the
    edge does not pull in black;
  * alpha: "scale4x" = Scale4x of the original's alpha (crisp, smooth outline; figures), or "nearest" = each
    original pixel's alpha as a 4x4 block (tiles keep the original's exact outline, so they still tessellate);
  * --context N (tiles): the tile is upscaled inside an N-ring patch of random tiles of its group, then
    cropped, so the model sees grass on every side instead of a cut edge.
Each sprite sits in a cell with 1 original pixel (4 texels) of bled colour around it and every cell is
4-aligned, so the renderer's mipmaps (level 2 = 1 texel per original pixel) never mix two sprites.

Output (git-ignored, served by the play server): viewer/play/atlas/hires/<set>/<method>/<FILE>.json + _<n>.png
    {"scale": 4, "sheets": [...], "images": {index: [sheet, x, y, w, h, anchor_x, anchor_y, mirror_of, iso]}}
x, y, w, h, anchor in hi-res texels (= 4x the original's); mirrored images point at their original (the
renderer flips it). viewer/play/atlas/hires/index.json lists the sets and methods built.
"""
import argparse
import json
import os
import random
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "extracted", "sprites")
OUT = os.path.join(ROOT, "viewer", "play", "atlas", "hires")
DEFAULT_MODELS = os.environ.get("ZEUS_ESRGAN", os.path.join(ROOT, ".cache", "esrgan"))   # git-ignored; docs/play/hires.md
ML = {"ultrasharp": "4x-UltraSharp", "remacri": "4x_foolhardy_Remacri", "siax": "4x_NMKD-Siax_200k",
      "superscale": "4x_NMKD-Superscale-SP_178000_G"}
METHODS = ["nearest", "scale4x", *ML]
LABELS = {"original": "Original", "nearest": "Nearest 4x", "scale4x": "Scale4x (EPX)", "ultrasharp": "4x-UltraSharp",
          "remacri": "Remacri", "siax": "NMKD-Siax", "superscale": "NMKD-Superscale"}
S = 4                 # the models' scale
OS = 4                # output scale (--scale 2: the 4x result box-filtered to 2x; 2 texels per world pixel is
                      # already finer than the screen at 100-200 % zoom, and a quarter of the memory)
PAD = 1               # cell padding, original pixels
SHEET = 4096          # hi-res texels
# Dithered foliage (bugs.md 129): the original's vine / olive / orange tree art is single-pixel noise (black,
# white and magenta dots meant to blend at 100 %); the model sharpens each dot into a highlight or a hole, so at
# 200-500 % zoom the trees read as black/white speckle with pink fringes. Their colour goes into the model
# through a Gaussian blur (sigma in original pixels) first; the outline (alpha) is untouched.
PREBLUR = {("Zeus_General", "SPR_GRAPEVINE"): 0.5, ("Zeus_General", "SPR_OLIVE_TREE"): 0.5,
           ("Poseidon_Loaded", "SPR_FRUIT_TREE"): 0.5}
TERRAIN_GROUPS = ["SPR_IN_FILL1", "SPR_IN_FILL2", "SPR_GRASS", "SPR_MEADOW", "SPR_MEADOW_DESERT",
                  "SPR_MEADOW_LIGHT_GRASS", "SPR_THICK_GRASS", "SPR_THICK_GRASS_RIM", "SPR_THICK_GRASS_NOHAT"]


# --- image ops ---------------------------------------------------------------------------------------
def bleed(rgb, filled, n):
    """Fill pixels not in `filled` from the average of filled 8-neighbours, n rings out."""
    rgb = rgb.copy(); filled = filled.copy()
    for _ in range(n):
        if filled.all():
            break
        p = np.pad(rgb * filled[..., None], ((1, 1), (1, 1), (0, 0)))
        f = np.pad(filled, 1).astype(np.float32)
        h, w = filled.shape
        acc = sum(p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        cnt = sum(f[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        new = ~filled & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        filled |= new
    return rgb


def scale2x(img):
    """EPX / Scale2x on an HxWxC array (exact colour compare)."""
    p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode="edge")
    E = p[1:-1, 1:-1]; B = p[:-2, 1:-1]; H = p[2:, 1:-1]; D = p[1:-1, :-2]; F = p[1:-1, 2:]
    eq = lambda x, y: np.all(x == y, axis=2)
    c = ~eq(B, H) & ~eq(D, F)
    e0 = np.where((c & eq(D, B))[..., None], D, E); e1 = np.where((c & eq(B, F))[..., None], F, E)
    e2 = np.where((c & eq(D, H))[..., None], D, E); e3 = np.where((c & eq(H, F))[..., None], F, E)
    h, w, ch = img.shape
    out = np.zeros((h * 2, w * 2, ch), img.dtype)
    out[0::2, 0::2] = e0; out[0::2, 1::2] = e1; out[1::2, 0::2] = e2; out[1::2, 1::2] = e3
    return out


def near4(a):
    return a.repeat(S, 0).repeat(S, 1)


def shadow(a):
    """Pure red = shadow: black at 50% alpha (tools/play_atlas.py)."""
    a = a.copy()
    m = (a[..., 0] == 255) & (a[..., 1] == 0) & (a[..., 2] == 0) & (a[..., 3] == 255)
    a[m] = (0, 0, 0, 128)
    return a


class Models:
    def __init__(self, folder, names):
        import torch, spandrel
        self.torch = torch
        self.dev = "mps" if torch.backends.mps.is_available() else "cpu"
        self.m = {n: spandrel.ModelLoader().load_from_file(os.path.join(folder, ML[n] + ".pth")).to(self.dev).eval()
                  for n in names if n in ML}

    def run(self, name, rgb, tile=192, lap=16):     # float HxWx3 0..1 -> 4x
        """Big inputs go through in tile x tile pieces overlapping by `lap` px (each piece keeps only its
        inner part), so the 4x activations fit in memory."""
        h, w = rgb.shape[:2]
        if h <= tile + 2 * lap and w <= tile + 2 * lap:
            return self._run(name, rgb)
        out = np.zeros((h * S, w * S, 3), np.float32)
        for y0 in range(0, h, tile):
            for x0 in range(0, w, tile):
                ya, xa = max(0, y0 - lap), max(0, x0 - lap)
                yb, xb = min(h, y0 + tile + lap), min(w, x0 + tile + lap)
                o = self._run(name, rgb[ya:yb, xa:xb])
                y1, x1 = min(h, y0 + tile), min(w, x0 + tile)
                out[y0 * S:y1 * S, x0 * S:x1 * S] = o[(y0 - ya) * S:(y1 - ya) * S, (x0 - xa) * S:(x1 - xa) * S]
        return out

    def _run(self, name, rgb):
        t = self.torch.from_numpy(np.ascontiguousarray(rgb, np.float32)).permute(2, 0, 1)[None].to(self.dev)
        with self.torch.no_grad():
            o = self.m[name](t)
        return o[0].permute(1, 2, 0).clamp(0, 1).cpu().numpy()


def upscale(method, src, models, alpha_mode, ctx=None, blur=0):
    """upscale4, at OS texels per original pixel."""
    o = upscale4(method, src, models, alpha_mode, ctx, blur)
    return o if OS == S else down(o, src[..., 3], method, alpha_mode)


def upscale4(method, src, models, alpha_mode, ctx=None, blur=0):
    """src: HxWx4 uint8 (shadow already converted), padded by >= PAD. ctx: optional (patch rgba, (x, y)) =
    the model's input with neighbours; (x, y) = where src's top-left sits in it. Returns 4x HxWx4 uint8 with
    the colour of transparent texels bled from opaque ones (for mipmapping)."""
    h, w = src.shape[:2]
    a = src[..., 3]
    if method == "nearest" or alpha_mode == "nearest":
        alpha = near4(a[..., None])[..., 0]
    else:
        alpha = scale2x(scale2x(a[..., None]))[..., 0]
    if method in ("nearest", "scale4x") and alpha_mode == "scale4x":
        o = near4(src) if method == "nearest" else scale2x(scale2x(src))
        alpha = o[..., 3]
        rgb = o[..., :3].astype(np.float32) / 255
        rgb = bleed(rgb, o[..., 3] > 0, 2 * S + 2)
    else:
        base = src if ctx is None else ctx[0]
        bb = base[..., 3] == 255
        filled = bleed(base[..., :3].astype(np.float32) / 255, bb, 12)
        if blur:                                     # PREBLUR: dithered foliage
            from PIL import ImageFilter
            q = Image.fromarray((filled * 255 + 0.5).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur))
            filled = np.asarray(q).astype(np.float32) / 255
        if method == "nearest":
            rgb = near4(filled)
        elif method == "scale4x":
            q = (filled * 255 + 0.5).astype(np.uint8)
            rgb = scale2x(scale2x(q)).astype(np.float32) / 255
        else:
            rgb = models.run(method, filled)
        if ctx is not None:
            x, y = ctx[1]
            rgb = rgb[y * S:(y + h) * S, x * S:(x + w) * S]
    out = np.dstack([(rgb * 255 + 0.5).clip(0, 255).astype(np.uint8), alpha])
    sh = alpha == 128                                # shadow texels: black
    out[sh, :3] = 0
    return out


# --- inputs ------------------------------------------------------------------------------------------
_atlas = {}
def atlas(file):
    if file not in _atlas:
        a = json.load(open(os.path.join(SRC, file, "atlas.json")))
        _atlas[file] = ({im["index"]: im for im in a["images"]}, a)
    return _atlas[file][0]


def group_indices(file, group):
    return sorted(k for k, im in atlas(file).items() if im["group"] == group)


def walker_specs(role):
    wm = json.load(open(os.path.join(ROOT, "data", "play", "walkers.json")))["roles"][role]
    out = []
    def blk(b, file):
        if not b or b.get("start") is None:
            return
        n = (b.get("frames") or 1) * (b.get("dirs") or 8)
        out.append((b.get("file") or file, b["start"], b["start"] + n - 1))
    f = wm["file"]
    blk(wm.get("walk"), f); blk(wm.get("die"), f)
    for c in (wm.get("carry") or {}).values():         # carry variants: a block, or {walk: block}
        blk(c if c.get("start") is not None else c.get("walk"), c.get("file", f))
    return out


def parse_specs(specs):
    by_file = {}
    for s in specs:
        if s.startswith("walker:"):
            for file, a, b in walker_specs(s[7:]):
                by_file.setdefault(file, set()).update(range(a, b + 1))
        elif "@" in s:
            file, g = s.split("@", 1)
            by_file.setdefault(file, set()).update(group_indices(file, g))
        elif ":" not in s:                           # a whole atlas file
            by_file.setdefault(s, set()).update(atlas(s))
        else:
            file, r = s.split(":", 1)
            a, _, b = r.partition("-")
            by_file.setdefault(file, set()).update(range(int(a), int(b or a) + 1))
    return by_file


def down(o, a, method, alpha_mode):
    """The 4x result at OS: colour = box mean (transparent texels carry bled colour), alpha straight from
    the original at OS (nearest: blocks, so tiles still tessellate; else Scale2x: a crisp outline)."""
    k = S // OS
    h, w = o.shape[0] // k, o.shape[1] // k
    rgb = o[..., :3].astype(np.float32).reshape(h, k, w, k, 3).mean((1, 3))
    if method == "nearest" or alpha_mode == "nearest":
        alpha = a.repeat(OS, 0).repeat(OS, 1)
    else:
        alpha = a[..., None]
        for _ in range(OS.bit_length() - 1):
            alpha = scale2x(alpha)
        alpha = alpha[..., 0]
    out = np.dstack([(rgb + 0.5).clip(0, 255).astype(np.uint8), alpha])
    out[alpha == 128, :3] = 0                        # shadow texels: black
    return out


def load_png(file, im):
    return shadow(np.array(Image.open(os.path.join(SRC, file, im["png"])).convert("RGBA")))


def context_patch(file, idx, ring, rng):
    """The tile with `ring` rings of random same-group 1x1 tiles around it, drawn back to front."""
    ims = atlas(file)
    me = ims[idx]
    pool = [k for k in group_indices(file, me["group"]) if not ims[k].get("mirror_of") and ims[k]["height"] <= 40]
    W, Hh = 58 + 60 * ring, 30 + 30 * ring + 40     # room for tufts above the back row
    patch = np.zeros((Hh + 2 * ring * 15 + 40, W + 2 * ring * 30, 4), np.uint8)
    ox, oy = ring * 30 + ring * 30, ring * 30 + 40                   # where the centre tile's diamond box goes
    def put(arr, px, py):
        h, w = arr.shape[:2]
        x0, y0 = ox + px, oy + py + 30 - h
        reg = patch[y0:y0 + h, x0:x0 + w]
        m = arr[..., 3] > 0
        reg[m] = arr[m]
    cells = [(dx, dy) for dy in range(-ring, ring + 1) for dx in range(-ring, ring + 1) if (dx, dy) != (0, 0)]
    for dx, dy in sorted(cells, key=lambda c: (c[0] + c[1], c[0])):
        k = rng.choice(pool)
        put(load_png(file, ims[k]), (dx - dy) * 30, (dx + dy) * 15)
    src = load_png(file, me)
    put(src, 0, 0)                                   # the tile itself last: its own pixels are intact
    h = src.shape[0]
    return patch, (ox, oy + 30 - h)


# --- packing -----------------------------------------------------------------------------------------
def flat_tile(file, im):
    """A sprite that must tessellate with its neighbours, so it keeps the original's exact outline: every
    Zeus_Terrain tile (taller ones too: a tree or tuft tile has a ground diamond, and Scale2x alpha rounds its
    staircase corners so neighbours leave dotted gaps, bugs.md 87), and every interface piece (16 px panel
    tiles, bugs.md 74)."""
    return file in ("Zeus_Interface", "Zeus_Terrain")


def build_set(name, specs, methods, models, alpha_mode, ctx_ring, only_file=None):
    """All the set's sprites, every file, packed together on shared sheets <name>_<n>.png; one json per file.
    alpha_mode "auto": nearest for flat ground tiles (flat_tile), scale4x for the rest. The context ring is
    only used for 1x1 ground tiles (58 px wide, the size context_patch builds)."""
    by_file = parse_specs(specs)
    rng = random.Random(1)
    items = []                                       # (file, index) of every stored (non-mirror) sprite
    for file, idxs in sorted(by_file.items()):
        ims = atlas(file)
        base = {i for i in idxs if i in ims and not ims[i].get("mirror_of") and ims[i]["width"] and ims[i]["height"]}
        base |= {ims[i]["mirror_of"] for i in idxs if i in ims and ims[i].get("mirror_of")}
        items += [(file, i) for i in sorted(base) if ims[i].get("png") and ims[i]["width"] and ims[i]["height"]]
    # shelf packing in original pixels; a sheet is SHEET texels = SHEET/OS original pixels
    lim = SHEET // OS
    dims = {(f, i): (atlas(f)[i]["width"] + 2 * PAD, atlas(f)[i]["height"] + 2 * PAD) for f, i in items}
    order = sorted(items, key=lambda k: (-dims[k][1], -dims[k][0], k))
    place, sheet_n, x, y, row = {}, 0, 0, 0, 0
    for k in order:
        cw, ch = dims[k]
        if x + cw > lim:
            x, y, row = 0, y + row, 0
        if y + ch > lim:
            sheet_n, x, y, row = sheet_n + 1, 0, 0, 0
        place[k] = (sheet_n, x, y)
        x += cw; row = max(row, ch)
    heights = {}
    for k, (sn, _, py) in place.items():
        heights[sn] = max(heights.get(sn, 0), py + dims[k][1])
    mode = lambda f, im: ("nearest" if flat_tile(f, im) else "scale4x") if alpha_mode == "auto" else alpha_mode
    use_ctx = lambda f, im: ctx_ring and f == "Zeus_Terrain" and im["width"] == 58 and im["height"] <= 40
    for m in methods:
        sheets = [np.zeros((1 << max(0, (heights[n] * OS - 1).bit_length()), SHEET, 4), np.uint8) for n in range(sheet_n + 1)]
        entries = {f: {} for f in by_file}
        for done, (f, i) in enumerate(items):
            im = atlas(f)[i]
            a = load_png(f, im)
            src = np.zeros((a.shape[0] + 16, a.shape[1] + 16, 4), np.uint8)
            src[8:-8, 8:-8] = a
            if use_ctx(f, im):
                patch, (cx, cy) = context_patch(f, i, ctx_ring, rng)
                h, w = src.shape[:2]                  # the padded sprite + 8 px more context each side
                crop = patch[cy - 16:cy - 16 + h + 16, cx - 16:cx - 16 + w + 16]
                o = upscale(m, src, models, mode(f, im), (crop, (8, 8)))
            else:
                o = upscale(m, src, models, mode(f, im), blur=PREBLUR.get((f, im["group"]), 0))
            c = (8 - PAD) * OS
            cell = o[c:o.shape[0] - c, c:o.shape[1] - c]
            sn, px, py = place[(f, i)]
            sheets[sn][py * OS:py * OS + cell.shape[0], px * OS:px * OS + cell.shape[1]] = cell
            entries[f][i] = [sn, (px + PAD) * OS, (py + PAD) * OS, im["width"] * OS, im["height"] * OS,
                             im["anchor_x"] * OS, im["anchor_y"] * OS, None, im["iso_size"]]
            if done % 500 == 499:
                print(f"{name}/{m}: {done + 1}/{len(items)}", flush=True)
        d = os.path.join(OUT, name, m)
        os.makedirs(d, exist_ok=True)
        names = []
        for n, sh in enumerate(sheets):
            fn = f"{name}_{n}.png"
            Image.fromarray(sh, "RGBA").save(os.path.join(d, fn), compress_level=3)
            names.append(fn)
        for f, idxs in by_file.items():
            ims, e = atlas(f), entries[f]
            for i in idxs:
                im = ims.get(i)
                if im and im.get("mirror_of") in e:
                    b = e[im["mirror_of"]]
                    e[i] = b[:5] + [im["anchor_x"] * OS, im["anchor_y"] * OS, im["mirror_of"], im["iso_size"]]
            with open(os.path.join(d, f + ".json"), "w") as fh:
                json.dump({"scale": OS, "sheets": names, "images": e}, fh, separators=(",", ":"))
            print(f"{name}/{m}/{f}: {len(e)} images", flush=True)
        print(f"{name}/{m}: sheets {[sh.shape[:2] for sh in sheets]}", flush=True)
    return sorted(by_file)


def patch_set(name, specs, methods, models, alpha_mode):
    """--patch: re-run only the listed sprites of an existing set and write them into its master sheets at the
    cells they already have (build_set's packing is deterministic, so a full rebuild gives the same sheets);
    for changes that touch a few sprites (PREBLUR) without the whole set's model run."""
    by_file = parse_specs(specs)
    mode = lambda f, im: ("nearest" if flat_tile(f, im) else "scale4x") if alpha_mode == "auto" else alpha_mode
    for m in methods:
        d = os.path.join(OUT, name, m)
        sheets, n = {}, 0
        for f, idxs in sorted(by_file.items()):
            ent = json.load(open(os.path.join(d, f + ".json")))
            assert ent["scale"] == OS, "patch at the masters' scale (--scale)"
            for i in sorted(idxs):
                e, im = ent["images"].get(str(i)), atlas(f).get(i)
                if not e or e[7] is not None or not im:
                    continue                          # mirrors point at their original
                sh = ent["sheets"][e[0]]
                if sh not in sheets:
                    sheets[sh] = np.array(Image.open(os.path.join(d, sh)).convert("RGBA"))
                a = load_png(f, im)
                src = np.zeros((a.shape[0] + 16, a.shape[1] + 16, 4), np.uint8)
                src[8:-8, 8:-8] = a
                o = upscale(m, src, models, mode(f, im), blur=PREBLUR.get((f, im["group"]), 0))
                c = (8 - PAD) * OS
                cell = o[c:o.shape[0] - c, c:o.shape[1] - c]
                x0, y0 = e[1] - PAD * OS, e[2] - PAD * OS
                sheets[sh][y0:y0 + cell.shape[0], x0:x0 + cell.shape[1]] = cell
                n += 1
        for sh, arr in sheets.items():
            Image.fromarray(arr, "RGBA").save(os.path.join(d, sh), compress_level=3)
        print(f"{name}/{m}: patched {n} sprites on {len(sheets)} sheets", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=DEFAULT_MODELS, help="folder with the .pth weights (+ venv/)")
    ap.add_argument("--methods", default=",".join(METHODS))
    ap.add_argument("--scale", type=int, default=4, choices=(2, 4), help="output texels per original pixel")
    ap.add_argument("--out", default=OUT, help="output folder (default: the one play mode serves)")
    ap.add_argument("--patch", action="store_true", help="re-run only the listed sprites into an existing set")
    ap.epilog = "then: --set NAME [--alpha A] [--context N] SPEC ... (repeatable)"
    args, rest = ap.parse_known_args()
    globals()["OUT"] = args.out
    globals()["OS"] = args.scale
    methods = [m for m in args.methods.split(",") if m]
    if any(m in ML for m in methods):
        try:
            import spandrel  # noqa: F401
        except ImportError:
            py = os.path.join(args.models, "venv", "bin", "python")
            if os.path.exists(py) and not os.environ.get("UPSCALE_REEXEC"):
                os.environ["UPSCALE_REEXEC"] = "1"
                os.execv(py, [py] + sys.argv)
            sys.exit(f"spandrel not found; pass --models DIR with DIR/venv (or drop the ML methods)")
    sets, cur = [], None
    it = iter(rest)
    for t in it:
        if t == "--set":
            cur = {"name": next(it), "alpha": "scale4x", "context": 0, "specs": []}; sets.append(cur)
        elif t == "--alpha": cur["alpha"] = next(it)
        elif t == "--context": cur["context"] = int(next(it))
        else: cur["specs"].append(t)
    if not sets:
        sets = [{"name": "walker", "alpha": "scale4x", "context": 0, "specs": ["walker:immigrant"]},
                {"name": "terrain", "alpha": "nearest", "context": 1,
                 "specs": [f"Zeus_Terrain@{g}" for g in TERRAIN_GROUPS]}]
    models = Models(args.models, methods) if any(m in ML for m in methods) else None
    idx_path = os.path.join(args.out, "index.json")
    try:
        index = json.load(open(idx_path))
    except (OSError, ValueError):
        index = {"labels": LABELS, "sets": {}}
    if args.patch:
        for s in sets:
            patch_set(s["name"], s["specs"], methods, models, s["alpha"])
        return
    for s in sets:
        files = build_set(s["name"], s["specs"], methods, models, s["alpha"], s["context"])
        old = index["sets"].get(s["name"], {}).get("methods", [])
        index["sets"][s["name"]] = {"files": files, "methods": [m for m in METHODS if m in set(old) | set(methods)],
                                    "alpha": s["alpha"], "context": s["context"], "specs": s["specs"]}
    index["labels"] = LABELS
    os.makedirs(args.out, exist_ok=True)
    with open(idx_path, "w") as f:
        json.dump(index, f, indent=1)


if __name__ == "__main__":
    main()
