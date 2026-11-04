"""Font upscaling comparison sheet (docs/play/hires.md "Fonts"): one sample sentence in several of the original's
fonts, per method, from the 4x font masters of tools/upscale_sprites.py, shown at 2x (the 4x halved, as play mode
samples them at 200 % zoom).

    python3 tools/font_samples.py [MASTERS=extracted/hires] [OUT=extracted/hires/fonts_sample.png]
"""
import json, os, sys
from PIL import Image, ImageDraw
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = sys.argv[1] if len(sys.argv) > 1 else os.path.join(R, "extracted", "hires")
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(H, "fonts_sample.png")
F = json.load(open(f"{R}/data/play/fonts.json"))
cm = F["charmap"]
def glyphs(method):
    j = json.load(open(f"{H}/fonts/{method}/Zeus_Fonts.json"))
    sheets = [Image.open(f"{H}/fonts/{method}/{s}") for s in j["sheets"]]
    return j, sheets
METHODS = [m for m in ("nearest", "scale4x", "remacri") if os.path.exists(f"{H}/fonts/{m}/Zeus_Fonts.json")]
data = {m: glyphs(m) for m in METHODS}
text = "Population 3,250 - Jul 761 BC. Wise Hera, the city needs more workers!"
rows = []
for font in ("11C", "22C", "9LTBK", "11LTBLUE", "11CB"):
    f = F["fonts"][font]
    for m in METHODS:
        j, sheets = data[m]
        sc = j["scale"]
        W = sum((f["width"][cm[ord(c)] - 1] if cm[ord(c)] else f["draw"]["space"]) + f["draw"]["extra"] for c in text) * sc + 40
        img = Image.new("RGBA", (W, (f["draw"]["line_height"] + 14) * sc + 10), (196, 172, 128, 255))
        x = 10
        for c in text:
            g = cm[ord(c)] if ord(c) < len(cm) else 0
            if not g:
                x += (f["draw"]["space"] + f["draw"]["extra"]) * sc; continue
            idx = str(f["first"] + g - 1)
            if idx not in j["images"]:
                x += f["width"][g - 1] * sc; continue
            s, gx, gy, w, h = j["images"][idx][:5]
            im = sheets[s].crop((gx, gy, gx + w, gy + h))
            img.alpha_composite(im, (x, 5))
            x += (f["width"][g - 1] + f["draw"]["extra"]) * sc
        # shown at 2x screen scale: the 4x result halved (what play mode would sample at 200 % zoom)
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        rows.append((f"{font} {m}", img))
Wt = max(r[1].width for r in rows) + 150; Ht = sum(r[1].height for r in rows)
sheet = Image.new("RGBA", (Wt, Ht), (255, 255, 255, 255)); d = ImageDraw.Draw(sheet); y = 0
for label, im in rows:
    d.text((4, y + 4), label, fill=(0, 0, 0)); sheet.alpha_composite(im, (150, y)); y += im.height
sheet.save(out)
print(sheet.size)
