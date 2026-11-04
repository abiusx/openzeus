"""Pack the original's extracted sprites into WebGL texture sheets for play mode (docs/play-mode.md).

    python3 tools/play_atlas.py [FILE ...]      (default: the files play mode uses)

Reads extracted/sprites/<FILE>/atlas.json + PNGs, writes viewer/play/atlas/<FILE>_<n>.png (4096x4096
sheets, shelf packing, 1 px gap) and viewer/play/atlas/<FILE>.json:
    {"sheets": [names], "images": {index: [sheet, x, y, w, h, anchor_x, anchor_y, mirror_of, iso_size, blend_shift]},
     "groups": {name: [first index, count]}, "blend": 1 when the file has alpha-masked images}
Mirrored images (atlas mirror_of) are not stored again: the renderer flips the original. Shadow
pixels (pure red) become black at 50% alpha. blend_shift = 1 for a mirrored image whose original has an alpha mask
(gods, monsters, heroes, satyrs, destruction): the exe draws those with FUN_00414190 (sprite_dispatch 0x005ACF50,
image +0x33 compressed with an alpha table +0x40), which puts pixel x of a row at width - x, i.e. 1 px right of
the exact mirror (refs/zeus-poseidon-arm64 native_blending.cpp; oracle 1H-follower, bugs.md 245).
Alpha-masked images are stored as the exe blends them (draw_runs_blended 0x00413E30 and its mirrored / clipped
twins: out = (a * image + (31 - a) * ground) >> 5 per 5-bit channel, a = 0 not drawn, no shadow test): an opaque
pixel (a = 31) one 5-bit step darker, exact; a partly transparent one with alpha (a + 1) / 32 and colour
image * a / (a + 1), so that play mode's premultiplied blend gives a / 32 image + (31 - a) / 32 ground (the floor
of the 5-bit sum not copied). See blended().
The output is the original game's art: viewer/play/atlas is git-ignored, rebuild with this tool.
"""
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "extracted", "sprites")
OUT = os.path.join(ROOT, "viewer", "play", "atlas")
DEFAULT = ["Zeus_Terrain", "Zeus_General", "SprMain", "SprAmbient", "Poseidon_Loaded", "Zeus_Interface",
           "destruction", "Zeus_Greek", "Poseidon_Unloaded", "Zeus_Unloaded", "PoseidonImps"]
NO_SHADOW = ("Zeus_Interface", "Zeus_Fonts")
SIZE = 4096
GAP = 1


def shadow(img):
    """Pure red 0x7C00 (255,0,0 after our 5->8 bit expansion) is the shadow colour: the game halves the
    pixel already drawn there (refs/zeus-poseidon-arm64 native.cpp put_run_pixel), i.e. black at 50%."""
    import numpy as np
    a = np.array(img)
    m = (a[..., 0] == 255) & (a[..., 1] == 0) & (a[..., 2] == 0) & (a[..., 3] == 255)
    if m.any():
        a[m] = (0, 0, 0, 128)
        img = Image.fromarray(a, "RGBA")
    return img


def blended(img):
    """an alpha-masked picture as draw_runs_blended 0x00413E30 puts it on the screen (see the module doc)"""
    import numpy as np
    a = np.array(img).astype(np.int32)
    a5 = a[..., 3] >> 3                                   # sg3.py expands the 5-bit alpha as (a << 3) | (a >> 2)
    s5 = a[..., :3] >> 3                                  # and the colour the same way
    full = a5 == 31
    out = a.copy()
    d5 = (31 * s5) >> 5                                   # a = 31: one step darker
    out[..., :3] = np.where(full[..., None], (d5 << 3) | (d5 >> 2), out[..., :3])
    part = (a5 > 0) & ~full
    w = a5[..., None] / np.maximum(a5[..., None] + 1, 1)
    out[..., :3] = np.where(part[..., None], np.rint(a[..., :3] * w), out[..., :3])
    out[..., 3] = np.where(part, np.rint(255 * (a5 + 1) / 32), np.where(a5 == 0, 0, out[..., 3]))
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def alpha_masked(a):
    """indices of the images whose pixels come with an alpha mask (sg3 record +68 alpha length > 0)"""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from sg3 import Sg3
    p = os.path.join(ROOT, "zeus-original", "app", "DATA", a["file"])
    if not os.path.exists(p):
        return set()
    return {im["index"] for im in Sg3(p).images[1:] if im["alpha_len"] > 0}


def pack(name):
    a = json.load(open(os.path.join(SRC, name, "atlas.json")))
    masked = alpha_masked(a)
    ims = [i for i in a["images"] if not i.get("mirror_of") and i["width"] and i["height"]]
    ims.sort(key=lambda i: (-i["height"], -i["width"], i["index"]))
    sheets, place = [], {}
    sheet = None
    x = y = row_h = 0
    for im in ims:
        w, h = im["width"], im["height"]
        if sheet is None or x + w > SIZE:
            x, y, row_h = 0, y + row_h + GAP, 0
        if sheet is None or y + h > SIZE:
            sheet = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
            sheets.append(sheet)
            x = y = row_h = 0
        try:
            src = Image.open(os.path.join(SRC, name, im["png"])).convert("RGBA")
        except (OSError, KeyError):
            continue
        if im["index"] in masked:
            src = blended(src)
        elif name not in NO_SHADOW:
            src = shadow(src)
        sheet.paste(src, (x, y))
        place[im["index"]] = [len(sheets) - 1, x, y, w, h, im["anchor_x"], im["anchor_y"], None, im["iso_size"]]
        x += w + GAP
        row_h = max(row_h, h)
    for im in a["images"]:                          # mirrored images point at their original
        m = im.get("mirror_of")
        if m and m in place:
            p = place[m]
            place[im["index"]] = [p[0], p[1], p[2], p[3], p[4], im["anchor_x"], im["anchor_y"], m, im["iso_size"],
                                  1 if m in masked else 0]
    os.makedirs(OUT, exist_ok=True)
    names = []
    for n, s in enumerate(sheets):
        bbox = s.getbbox() or (0, 0, 1, 1)
        hgt = 1 << max(0, (bbox[3] - 1).bit_length())  # trim the last sheet to a power of two
        s = s.crop((0, 0, SIZE, min(SIZE, max(hgt, 1))))
        fn = f"{name}_{n}.png"
        s.save(os.path.join(OUT, fn), optimize=False, compress_level=3)
        names.append(fn)
    groups = {}                                     # group name -> [first index, count]
    for im in a["images"]:
        g = groups.setdefault(im["group"], [im["index"], 0])
        g[0] = min(g[0], im["index"])
        g[1] += 1
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump({"sheets": names, "images": place, "groups": groups, **({"blend": 1} if masked else {})}, f,
                  separators=(",", ":"))
    return len(place), len(sheets)


if __name__ == "__main__":
    for name in sys.argv[1:] or DEFAULT:
        n, s = pack(name)
        print(f"{name}: {n} images in {s} sheets")
