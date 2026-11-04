"""GPU-compressed copies of play mode's texture sheets (docs/play/hires.md "GPU-compressed sheets").

    python3 tools/hires_compress.py [--formats astc,bc7] [--bc7enc PATH] [--hires DIR] [SET...]
    python3 tools/hires_compress.py --originals [--formats astc,bc7] [--bc7enc PATH] [--atlas DIR]

Hi-res sets (tools/hires_derive.py, 2x copies): for each sheet <set>_<n>.png it writes <set>_<n>.astc.bin and/or
<set>_<n>.bc7.bin: the sheet padded to 4096 x 4096 and every mip level down to 1 x 1, levels back to back from
level 0, each in 4x4 blocks of 16 bytes (level l is (4096 >> l) square, ceil(side / 4)^2 blocks, so the reader
needs no table). The mips use the renderer's rule (gl.js MIP_FS): colour = alpha-weighted mean of the 2x2,
alpha = their max. index.json gets "compressed": {"astc": ..., "bc7": ...} per set.

--originals: the original's own atlas sheets (tools/play_atlas.py, viewer/play/atlas/<FILE>_<n>.png, 4096 wide,
drawn 1:1 with no mips): level 0 only, as <FILE>_<n>.astc.bin / .bc7.bin, listed in viewer/play/atlas/compressed.json
{"version", "formats": {fmt: {block, suffix}}, "sheets": {png name: [w, h]}}. The interface and font atlases
(LOSSLESS) are left out: their pixels are compared 1:1 with the original's screenshots (docs/play/ui.md); so are
the files with alpha-masked pictures (atlas json "blend": gods, monsters, heroes, destruction, PoseidonImps): their
partly transparent pixels carry the exe's blend weights (tools/play_atlas.py blended()), which a lossy copy and the
shader's alpha snap would undo.

Play mode takes ASTC when the browser has WEBGL_compressed_texture_astc (Apple GPUs, most mobiles), else BC7
with EXT_texture_compression_bptc (Windows/Linux desktop GPUs), else the PNGs; `?tex=astc|bc7|png` in the page
url forces one. No PNG decode, no mip pass, 1 byte per texel.

Encoders (docs/play/hires.md "Reproduce from scratch"):
  astc  the astc-encoder-py binding of ARM's astcenc (pip install astc-encoder-py==0.1.12 numpy pillow), 4x4 LDR,
        preset medium; it segfaulted with more than ~8 threads on an 18-core M5 Pro, so threads=8.
  bc7   bc7enc_rdo's command-line tool built with bc7e.ispc (all BC7 modes), `-U -u4` (quality 4 of 6: 6 took 3.6x
        as long for 6 % less error), one process per core, DX10 .dds out; --bc7enc PATH or $BC7ENC.
"""
import argparse
import concurrent.futures as cf
import json
import os
import struct
import subprocess
import tempfile
import time

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDE, LEVELS, THREADS = 4096, 13, 8
LOSSLESS = ("Zeus_Interface", "Zeus_Fonts")       # --originals: kept as PNG (pixel-exact UI and text)
FORMATS = {"astc": {"block": [4, 4], "suffix": ".astc.bin"}, "bc7": {"block": [4, 4], "suffix": ".bc7.bin"}}


def content_version(paths):
    """A version number from the files' bytes (sheet urls carry ?v=<version>: no stale cached copies). From the
    content, not the clock, so the same inputs give the same json (tools/assets.py: build and pack identical)."""
    import hashlib
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(os.path.basename(p).encode() + b"\0")
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
    return int(h.hexdigest()[:8], 16)


def sheet_files(hires, ix):
    """Every sheet file (png and compressed copies) of the hi-res sets in index.json ix."""
    out = []
    for name, S in ix["sets"].items():
        for m in S["methods"]:
            d = os.path.join(hires, name, m)
            for n in range(S.get("sheets", 0)):
                out += [p for p in [os.path.join(d, f"{name}_{n}.png")] + [os.path.join(d, f"{name}_{n}" + F["suffix"])
                        for F in FORMATS.values()] if os.path.exists(p)]
    return out


def mips(a):
    """Level 0 (uint8 SIDE x SIDE x 4) and every smaller level, as MIP_FS draws them."""
    out = [a]
    f = a.astype(np.float32)
    while f.shape[0] > 1:
        h = f.shape[0] // 2
        b = f.reshape(h, 2, h, 2, 4)
        al = b[..., 3]
        wt = al.sum((1, 3))
        rgb = (b[..., :3] * al[..., None]).sum((1, 3)) / np.maximum(wt, 1)[..., None]
        rgb[wt == 0] = 0
        f = np.dstack([rgb, al.max((1, 3))])
        out.append((f + 0.5).clip(0, 255).astype(np.uint8))
    return out


_ASTC = None


def encode_astc(img):
    """One image (h x w x 4 uint8, any size) -> ASTC 4x4 blocks."""
    global _ASTC
    import astc_encoder as A
    if _ASTC is None:
        _ASTC = A.ASTCContext(A.ASTCConfig(A.ASTCProfile.LDR, 4, 4, 1, A.ASTCQualityPreset.MEDIUM), threads=THREADS)
    h, w = img.shape[:2]
    d = _ASTC.compress(A.ASTCImage(A.ASTCType.U8, w, h, 1, np.ascontiguousarray(img).tobytes()), A.ASTCSwizzle())
    assert len(d) == ((w + 3) // 4) * ((h + 3) // 4) * 16, (w, h, len(d))
    return d


def dds_payload(path):
    """The block data of a .dds (skips the header, and the DX10 extension when present)."""
    b = open(path, "rb").read()
    assert b[:4] == b"DDS ", path
    off = 4 + struct.unpack_from("<I", b, 4)[0]
    if b[84:88] == b"DX10":
        off += 20
    return b[off:]


def encode_bc7(img, exe):
    """One image -> BC7 4x4 blocks with bc7enc_rdo (bc7e.ispc); sides below 4 are padded to one block."""
    h, w = img.shape[:2]
    H, W = max(4, (h + 3) // 4 * 4), max(4, (w + 3) // 4 * 4)
    if (H, W) != (h, w):
        p = np.zeros((H, W, 4), np.uint8)
        p[:h, :w] = img
        img = p
    with tempfile.TemporaryDirectory() as t:
        src, dst = os.path.join(t, "in.png"), os.path.join(t, "out.dds")
        Image.fromarray(img, "RGBA").save(src, compress_level=1)
        subprocess.run([exe, "-q", "-g", "-U", "-u4", src, dst], check=True, cwd=t,
                       stdout=subprocess.DEVNULL, env={**os.environ, "OMP_NUM_THREADS": "1"})
        d = dds_payload(dst)
    assert len(d) == (W // 4) * (H // 4) * 16, (w, h, len(d))
    return d


def load(path, fill=True):
    """A sheet with colour bled under its transparent texels (4 rings): the original's atlases have black there,
    and a 4x4 block mixing a bright sprite edge with black gap texels made BC7 get alpha wrong by > 63 on 599
    texels of Zeus_General_0 (40 bled; ASTC 22 / 31). Transparent texels are never drawn (gl.js discards alpha
    0), so this changes no picture. The hi-res sheets are already bled (tools/upscale_sprites.py)."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from upscale_sprites import bleed
    img = np.array(Image.open(path).convert("RGBA"))
    if not fill:
        return img
    img[..., :3] = (bleed(img[..., :3].astype(np.float32), img[..., 3] > 0, 4) + 0.5).clip(0, 255).astype(np.uint8)
    return img


def bc7_levels(args):
    path, out, exe, with_mips = args
    img = load(path, not with_mips)
    if with_mips:
        pad = np.zeros((SIDE, SIDE, 4), np.uint8)
        pad[:img.shape[0], :img.shape[1]] = img
        levels = mips(pad)
    else:
        levels = [img]
    data = b"".join(encode_bc7(lv, exe) for lv in levels)
    with open(out, "wb") as f:
        f.write(data)
    return out


def jobs_bc7(jobs, exe):
    """(png, out .bc7.bin, with mips) in parallel: one bc7enc process per core."""
    n = max(1, (os.cpu_count() or 4) - 2)
    with cf.ProcessPoolExecutor(n) as ex:
        for o in ex.map(bc7_levels, [(p, o, exe, m) for p, o, m in jobs]):
            print(f"bc7: {os.path.basename(o)}", flush=True)


def astc_file(path, out, with_mips):
    img = load(path, not with_mips)
    if with_mips:
        pad = np.zeros((SIDE, SIDE, 4), np.uint8)
        pad[:img.shape[0], :img.shape[1]] = img
        levels = mips(pad)
        assert len(levels) == LEVELS
    else:
        levels = [img]
    with open(out, "wb") as f:
        f.write(b"".join(encode_astc(lv) for lv in levels))
    print(f"astc: {os.path.basename(out)}", flush=True)


def run(jobs, formats, exe):
    """jobs: (png path, out path without suffix, with mips)."""
    if "astc" in formats:
        for p, o, m in jobs:
            astc_file(p, o + FORMATS["astc"]["suffix"], m)
    if "bc7" in formats:
        jobs_bc7([(p, o + FORMATS["bc7"]["suffix"], m) for p, o, m in jobs], exe)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hires", default=os.path.join(ROOT, "viewer", "play", "atlas", "hires"))
    ap.add_argument("--atlas", default=os.path.join(ROOT, "viewer", "play", "atlas"))
    ap.add_argument("--formats", default="astc,bc7")
    ap.add_argument("--bc7enc", default=os.environ.get("BC7ENC"))
    ap.add_argument("--originals", action="store_true", help="the original's atlases instead of the hi-res sets")
    ap.add_argument("sets", nargs="*")
    a = ap.parse_args()
    formats = [f for f in a.formats.split(",") if f]
    assert all(f in FORMATS for f in formats), formats
    if "bc7" in formats and not (a.bc7enc and os.path.exists(a.bc7enc)):
        ap.error("bc7 needs --bc7enc PATH (or $BC7ENC): bc7enc_rdo built with bc7e.ispc")
    if a.bc7enc:
        a.bc7enc = os.path.abspath(a.bc7enc)          # the encoder runs in a temporary folder
    t0 = time.time()
    if a.originals:
        jobs, sizes = [], {}
        for fn in sorted(os.listdir(a.atlas)):
            if not fn.endswith(".json") or fn == "compressed.json" or fn[:-5] in LOSSLESS:
                continue
            j = json.load(open(os.path.join(a.atlas, fn)))
            if j.get("blend"):                        # the exe's blended pictures: exact alpha (play_atlas.py)
                continue
            for s in j.get("sheets", []):
                w, h = Image.open(os.path.join(a.atlas, s)).size
                assert w % 4 == 0 and h % 4 == 0, s
                sizes[s] = [w, h]
                jobs.append((os.path.join(a.atlas, s), os.path.join(a.atlas, s[:-4]), False))
        run(jobs, formats, a.bc7enc)
        cp = os.path.join(a.atlas, "compressed.json")
        try:
            old = json.load(open(cp))
        except (OSError, ValueError):
            old = {"formats": {}}
        fm = {f: FORMATS[f] for f in formats if f in FORMATS} | {f: v for f, v in old.get("formats", {}).items() if f not in formats}
        with open(cp, "w") as f:
            json.dump({"version": content_version([os.path.join(a.atlas, s[:-4] + FORMATS[f]["suffix"]) for s in sizes
                                                   for f in fm if os.path.exists(os.path.join(a.atlas, s[:-4] + FORMATS[f]["suffix"]))]),
                       "formats": fm, "sheets": sizes}, f, indent=1)
    else:
        ix_path = os.path.join(a.hires, "index.json")
        ix = json.load(open(ix_path))
        for name in a.sets or list(ix["sets"]):
            S = ix["sets"][name]
            jobs = []
            for m in S["methods"]:
                d = os.path.join(a.hires, name, m)
                jobs += [(os.path.join(d, f"{name}_{n}.png"), os.path.join(d, f"{name}_{n}"), True) for n in range(S["sheets"])]
            run(jobs, formats, a.bc7enc)
            S.setdefault("compressed", {})
            for f in formats:
                S["compressed"][f] = {**FORMATS[f], "side": SIDE, "levels": LEVELS}
        ix["version"] = content_version(sheet_files(a.hires, ix))   # sheet urls carry ?v=: no stale cached copies
        with open(ix_path, "w") as f:
            json.dump(ix, f, indent=1)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
