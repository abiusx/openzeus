"""Track 1E checks on the shots of tools/e1_check.mjs (docs/play/bugs.md): run after it.

    python3 tools/e1_check.py OUTDIR

- cart: the '?' (SPR_PROBLEM_ICONS + 11, extracted/sprites) must sit with its top-left on the waiting cart's tile
  point (the exe's place, re/oracle/runs/cartwait2/p1.bmp); best template match within 40 px, max channel error.
- bridge: pixels the ghost changed (bridge.png vs bridge0.png) must have red <= 7/31, blue <= 3/31 (the exe's AND 0x1FE3 on
  RGB555, as the oracle draws).
- minimap: every shown walker's 2-px cell black."""
import json, os, sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = sys.argv[1]
c = json.load(open(os.path.join(d, "cart.json")))
if c:
    im = np.asarray(Image.open(os.path.join(d, "cart.png")).convert("RGB")).astype(int)
    ic = Image.open(os.path.join(ROOT, "extracted/sprites/Zeus_General/SPR_PROBLEM_ICONS/00970.png")).convert("RGBA")
    if abs(c["scale"] - 1) > 1e-6:
        ic = ic.resize((round(ic.width * c["scale"]), round(ic.height * c["scale"])), Image.NEAREST)
    a = np.asarray(ic).astype(int)
    m = a[..., 3] > 0
    h, w = m.shape
    best = None
    for y in range(c["dpy"] - 40, c["dpy"] + 41):
        for x in range(c["dpx"] - 40, c["dpx"] + 41):
            if 0 <= y and 0 <= x and y + h <= im.shape[0] and x + w <= im.shape[1]:
                e = np.abs(im[y:y + h, x:x + w] - a[..., :3])[m].max()
                if best is None or e < best[0]:
                    best = (e, x, y)
    print(f"cart {c['id']} at ({c['x']},{c['y']}): expected top-left ({c['dpx']},{c['dpy']}), best match "
          f"({best[1]},{best[2]}) max error {best[0]}; minimap cells black {c['minimap'][1]}/{c['minimap'][0]}")
else:
    print("cart: no waiting cart in this save")
bp = os.path.join(d, "bridge.json")
if os.path.exists(bp):
    g = json.load(open(bp))
    a0 = np.asarray(Image.open(os.path.join(d, "bridge0.png")).convert("RGB")).astype(int)
    a1 = np.asarray(Image.open(os.path.join(d, "bridge.png")).convert("RGB")).astype(int)
    ch = np.abs(a1 - a0).max(axis=2) > 0
    box = np.zeros(ch.shape, bool)
    for x, y, w, h in (g or {}).get("boxes", []):
        box[max(0, y):y + h, max(0, x):x + w] = True
    px = a1[ch & box]
    ok = (px[:, 0] <= 58) & (px[:, 2] <= 25)
    print(f"bridge ghost: {len(g['pieces']) if g else 0} pieces, {int((ch & box).sum())} changed px in their boxes, "
          f"{int(ok.sum())} with red <= 58, blue <= 25 ({100 * ok.mean() if len(px) else 0:.1f} %); changed outside the boxes "
          f"{int((ch & ~box).sum())}")
