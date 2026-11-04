"""Compare an oracle screenshot (800x600 exe shot, view 0) with play mode at the exe's camera, pixel by pixel.

    python3 tools/oracle_view_compare.py SHOT.bmp URL COL ROW [--box X0,Y0,X1,Y1] [--out PNG]

URL is play mode of your own server on a COPY of a save (not a game in play), e.g. http://127.0.0.1:8799/play.html;
COL, ROW = the exe's top-left view cell (0x00DA2F64 / 0x00DA2F68, as poked in the scenario). Play mode is drawn
paused, in headless Chrome at dpr 1.25 with zoom 1/dpr (one device pixel per picture pixel), camera
(60 COL - 6870, 15 ROW - 30), in --view 2/6 (60 COL - 6810, 15 ROW - 60) (docs/play/rotation.md "Verification"); an odd
ROW (a poked camera; bugs.md 363) only lines up the tiles of even x + y (x 30 px less): poke even rows. Prints the share of the map area
(x 10..590, y 80..580) within 8 per channel, and of --box if given. Needs node >= 22, Chrome, Pillow, numpy.
--tex png (default) adds ?tex=png to URL: play mode's default original sprites are compressed (lossy) since 10-29.
Used for bugs.md 177 / 185 (docs/play/draw-order.md 7). --eval JS runs after the camera is set (a tool, a hover:
bugs.md 212 bridge ghost); --mask OTHER.bmp scores only the pixels where SHOT differs from OTHER; --green only the exe's green-tinted
ghost pixels (and their IoU with ours), both inside --box."""
import argparse, os, subprocess, tempfile
import numpy as np
from PIL import Image
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)

HERE = os.path.dirname(os.path.abspath(__file__))
JS = r"""
import { launch } from %r;
const [url, out, c, r, ev, view] = process.argv.slice(2);
const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
try {
  await b.open(url);
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && objBatch && objBatch.n > 0", 180000);
  await b.eval("P.playing && togglePlay(), 0");
  await new Promise(r => setTimeout(r, 1500));
  const q = +view === 2 || +view === 6;                   // views 2/6: cam (60c - 6810, 15r - 60) (docs/play/rotation.md "Verification")
  await b.eval(`while (VIEW !== ${+view}) rotateView(2); 0`);
  await new Promise(r => setTimeout(r, 1500));
  // an odd ROW (a poke only: bugs.md 363): the exe draws the tiles of even x + y 30 px left of the even-row rule and those
  // of odd x + y 30 px right of it (its screen rows shear apart); this lines up the even ones (half the map)
  await b.eval(`clampCam = () => {}; cam.zoom = 1 / devicePixelRatio; cam.x = 60 * ${c} - ${q ? 6810 : 6870} - 30 * (${r} & 1); cam.y = 15 * ${r} - ${q ? 60 : 30}; 0`);
  await new Promise(r => setTimeout(r, 1200));
  if (ev) { await b.eval(ev); await new Promise(r => setTimeout(r, 2500)); }
  await b.shot(out);
} finally { await b.close(); }
""" % os.path.join(HERE, "play_cdp.mjs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shot"); ap.add_argument("url"); ap.add_argument("col", type=int); ap.add_argument("row", type=int)
    ap.add_argument("--box"); ap.add_argument("--out"); ap.add_argument("--tex", default="png")
    ap.add_argument("--view", type=int, default=0, help="the exe's view 0/2/4/6 (COL ROW = that view's top-left cell)")
    ap.add_argument("--eval", default="", help="JS run in the page after the camera is set (e.g. a tool and hover)")
    ap.add_argument("--green", action="store_true", help="score only the exe's pixels in the 0x1FE3 tint range (a ghost), in --box")
    ap.add_argument("--mask", help="compare only where this exe shot differs from SHOT (e.g. the ghost: shot without it)")
    a = ap.parse_args()
    if a.row & 1:
        print("warning: odd ROW: the exe shears its screen rows apart (bugs.md 363): only tiles of even x + y line up")
    if a.tex and "tex=" not in a.url:
        a.url += ("&" if "?" in a.url else "?") + "tex=" + a.tex
    with tempfile.TemporaryDirectory() as d:
        js, png = os.path.join(d, "shot.mjs"), a.out or os.path.join(d, "play.png")
        open(js, "w").write(JS)
        subprocess.run(["node", js, a.url, png, str(a.col), str(a.row), a.eval, str(a.view)], check=True)
        ex = np.asarray(Image.open(oracle.shot(a.shot)).convert("RGB")).astype(int)
        pm = np.asarray(Image.open(png).convert("RGB")).astype(int)
    ok = np.abs(ex[80:580, 10:590] - pm[80:580, 10:590]).max(axis=2) <= 8
    print(f"map area within 8: {ok.mean() * 100:.1f} %")
    if a.box:
        x0, y0, x1, y1 = map(int, a.box.split(","))
        okb = np.abs(ex[y0:y1, x0:x1] - pm[y0:y1, x0:x1]).max(axis=2) <= 8
        print(f"box {a.box} within 8: {okb.mean() * 100:.1f} %")
    if a.mask or a.green:
        x0, y0, x1, y1 = map(int, a.box.split(",")) if a.box else (10, 80, 590, 580)
        e, p = ex[y0:y1, x0:x1], pm[y0:y1, x0:x1]
        m = np.ones(e.shape[:2], bool)
        if a.mask:
            m &= np.abs(e - np.asarray(Image.open(oracle.shot(a.mask)).convert("RGB")).astype(int)[y0:y1, x0:x1]).max(axis=2) > 0
        if a.green:                                # the AND 0x1FE3 tint (RGB555: red <= 7, blue <= 3 of 31), green >= 40
            m &= (e[..., 0] <= 56) & (e[..., 2] <= 24) & (e[..., 1] >= 40)
            mp = (p[..., 0] <= 63) & (p[..., 2] <= 31) & (p[..., 1] >= 40)
            print(f"tinted: exe {int(m.sum())} px, ours {int(mp.sum())}, IoU {(m & mp).sum() / max(1, (m | mp).sum()):.3f}")
        okm = np.abs(e - p).max(axis=2)[m] <= 8
        print(f"selected exe pixels ({int(m.sum())}): {okm.mean() * 100:.1f} % within 8")

if __name__ == "__main__":
    main()
