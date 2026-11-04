"""The README's hi-res examples: an original sprite (nearest, 2x) beside its hi-res version (downscaled to 2x).

  python3 tools/readme_media.py OUTDIR      # writes hires-house.png, hires-estate.png

Reads extracted/sprites/ (tools/assets.py build) and the 4x hi-res masters in extracted/hires/ (docs/play/hires.md;
not in the asset pack, so this is a maintainer tool).
"""
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HI = os.path.join(ROOT, "extracted/hires/buildings/remacri/")
PICS = ((1018, "SPR_B_HOUSE7", "house"), (1046, "SPR_B_ELITE_HOUSE4", "estate"))   # Zeus_General image numbers


def main(out):
    idx = json.load(open(HI + "Zeus_General.json"))
    os.makedirs(out, exist_ok=True)
    for i, grp, name in PICS:
        o = Image.open(os.path.join(ROOT, f"extracted/sprites/Zeus_General/{grp}/{i:05d}.png")).convert("RGBA")
        e = idx["images"][str(i)]
        h = Image.open(HI + idx["sheets"][e[0]]).convert("RGBA").crop((e[1], e[2], e[1] + e[3], e[2] + e[4]))
        size = (o.width * 2, o.height * 2)
        o2, h2 = o.resize(size, Image.NEAREST), h.resize(size, Image.LANCZOS)
        pad = 24
        c = Image.new("RGBA", (size[0] * 2 + pad * 3, size[1] + pad * 2), (0, 0, 0, 0))
        c.alpha_composite(o2, (pad, pad))
        c.alpha_composite(h2, (pad * 2 + size[0], pad))
        c.save(os.path.join(out, f"hires-{name}.png"), optimize=True)


if __name__ == "__main__":
    main(sys.argv[1])
