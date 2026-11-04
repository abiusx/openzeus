"""Ground under monument step tiles against an oracle shot (bugs.md 400; docs/play/monuments.md 3).

    python3 tools/step_ground_oracle.py SHOT.bmp URL COL ROW [--view V]

Play mode (YOUR OWN server on a save copy, e.g. a converted tutorial15.sav) at the exe's camera (as
tools/oracle_view_compare.py: headless Chrome, dpr 1.25, zoom 1/dpr, view V), read back with gl.readPixels right after
the page's frame three times: A without ground under the step tiles (the exe's image grid: FUN_00521520 puts only the
step picture there), B with our computed ground under them (window.stepGround emptied), C as A again (pixels that
differ between A and C animate and are left out). Of the pixels where A and B differ, prints how many match the exe
shot within 8 per channel in A and in B. Re/oracle/scenarios/tut15-steps.txt makes the shots.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import oracle  # noqa: E402

JS = r"""
import { launch } from %r;
import { writeFileSync } from "node:fs";
const [url, out, c, r, view] = process.argv.slice(2);
const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
try {
  await b.open(url);
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && window.Monuments && objBatch && objBatch.n > 0", 180000);
  await b.eval("P.playing && togglePlay(), setMuted(true), 0");
  await b.eval(`while (VIEW !== ${+view}) rotateView(2); 0`);
  await new Promise(r => setTimeout(r, 1500));
  const q = +view === 2 || +view === 6;
  await b.eval(`clampCam = () => {}; cam.zoom = 1 / devicePixelRatio; cam.x = 60 * ${c} - ${q ? 6810 : 6870}; cam.y = 15 * ${r} - ${q ? 60 : 30}; 0`);
  await new Promise(r => setTimeout(r, 1500));
  const grab = `new Promise(res => { const o = window.uiDraw; window.uiDraw = function (R) { o(R); window.uiDraw = o;
    const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
    const out = new Uint8Array(800 * 600 * 3);
    for (let y = 0; y < 600; y++) for (let x = 0; x < 800; x++) { const i = ((H - 1 - y) * W + x) * 4, j = (y * 800 + x) * 3;
      out[j] = px[i]; out[j + 1] = px[i + 1]; out[j + 2] = px[i + 2]; }
    let s = ''; for (let k = 0; k < out.length; k += 8192) s += String.fromCharCode.apply(null, out.subarray(k, k + 8192));
    res(btoa(s)); }; })`;
  const A = await b.eval(grab);
  await b.eval("window.__keep = window.stepGround, window.stepGround = () => new Set(), buildTerrain(), 0");
  await new Promise(r => setTimeout(r, 500));
  const B = await b.eval(grab);
  await b.eval("window.stepGround = window.__keep, buildTerrain(), 0");
  await new Promise(r => setTimeout(r, 500));
  const C = await b.eval(grab);
  for (const [k, v] of [["a", A], ["b", B], ["c", C]]) writeFileSync(out + k, Buffer.from(v, "base64"));
} finally { await b.close(); }
""" % os.path.join(HERE, "play_cdp.mjs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shot"); ap.add_argument("url"); ap.add_argument("col", type=int); ap.add_argument("row", type=int)
    ap.add_argument("--view", type=int, default=0)
    a = ap.parse_args()
    url = a.url + ("&" if "?" in a.url else "?") + "tex=png"
    with tempfile.TemporaryDirectory() as d:
        js, out = os.path.join(d, "g.mjs"), os.path.join(d, "px")
        open(js, "w").write(JS)
        subprocess.run(["node", js, url, out, str(a.col), str(a.row), str(a.view)], check=True)
        A, B, C = (np.frombuffer(open(out + k, "rb").read(), np.uint8).reshape(600, 800, 3).astype(int) for k in "abc")
    ex = np.asarray(Image.open(oracle.shot(a.shot)).convert("RGB")).astype(int)
    box = (slice(80, 580), slice(10, 590))                 # the map area (oracle_view_compare.py)
    A, B, C, ex = A[box], B[box], C[box], ex[box]
    diff = (A != B).any(axis=2) & (A == C).all(axis=2)
    live = ((A != C).any(axis=2)).sum()
    ma = (np.abs(A - ex).max(axis=2) <= 8)[diff].sum()
    mb = (np.abs(B - ex).max(axis=2) <= 8)[diff].sum()
    blk = lambda im: (im.max(axis=2) <= 4)[diff]                # noqa: E731  (nothing drawn: the clear colour)
    print(f"  of them black (nothing drawn) in ours without ground {int(blk(A).sum())}, in the exe shot {int(blk(ex).sum())}, "
          f"both {int((blk(A) & blk(ex)).sum())}")
    print(f"{os.path.basename(a.shot)} view {a.view}: {int(diff.sum())} px differ with / without the ground under the "
          f"steps ({int(live)} animating left out); exe-like within 8: without ground {int(ma)}, with ground {int(mb)}; "
          f"map area within 8: without {(np.abs(A - ex).max(axis=2) <= 8).mean() * 100:.1f} %, "
          f"with {(np.abs(B - ex).max(axis=2) <= 8).mean() * 100:.1f} %")


if __name__ == "__main__":
    main()
