"""The exe's alpha blend (draw_runs_blended 0x00413E30) in play mode against an oracle shot, pixel by pixel.

    python3 tools/e1_blend_check.py URL SHOT.bmp GROUND.bmp FILE INDEX X Y [--mirror] [--dpr 1.25]

SHOT: an oracle shot with the alpha-masked picture FILE:INDEX (atlas index, extracted/sprites/FILE) at top-left (X, Y)
(found with tools/e1_figure_check.py / oracle_match: the exe model scores 1.000); GROUND: a shot of the same view
without it (the ground under the picture equal to SHOT's around it: checked, the count is printed). URL: play mode's
server (your own port, any save), only for its files: the page loads viewer/play/gl.js (SpriteGL, the play-mode
shader and blend) and the play atlas (tools/play_atlas.py, blended()) into its own canvas in headless Chrome at dpr
1.25 (tools/play_cdp.mjs), one device pixel per picture pixel, draws the ground crop (as a picture: 5-bit values
expanded as play mode's sprites, v << 3 | v >> 2) and the picture on it, and reads the pixels back (gl.readPixels).
Prints for the picture's drawn pixels (alpha > 0): the exe model's own result vs SHOT ((a * image + (31 - a) * ground)
>> 5 per 5-bit channel, BMP v << 3), and play mode's 5-bit values (>> 3) vs SHOT: equal / 1 step off / more, split
into opaque (a = 31) and partly transparent ones. Used for bugs.md 245 / docs/play/gods.md (1H-god g_0080 Athena)."""
import argparse, base64, io, json, os, subprocess, tempfile

import numpy as np
from PIL import Image
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

JS = r"""
import { launch } from %r;
import { readFileSync } from "node:fs";
const [url, inp, dpr] = process.argv.slice(2);
const I = JSON.parse(readFileSync(inp, "utf8"));
const b = await launch({ width: 400, height: 400, dpr: +dpr });
try {
  await b.open(url);
  const r = await b.eval(`(async () => {
    const I = ${JSON.stringify(I)};
    await new Promise((ok, no) => { const s = document.createElement("script"); s.src = "play/gl.js"; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
    const img = async src => { const i = new Image(); i.src = src; await i.decode(); return i; };
    const W = I.w, H = I.h, d = devicePixelRatio;
    const c = document.createElement("canvas");
    c.style.cssText = "position:fixed;left:0;top:0;width:" + (W / d) + "px;height:" + (H / d) + "px";
    document.body.appendChild(c);
    const R = new SpriteGL(c);
    const g = R.addSheet(await img(I.ground)), a = R.addSheet(await img(I.sheet));
    const B = R.batch();
    B.push({ sheet: g, x: 0, y: 0, w: W, h: H }, 0, 0);
    B.push({ sheet: a, x: I.sx, y: I.sy, w: I.sw, h: I.sh, flip: I.flip }, I.px, I.py);
    R.begin({ x: 0, y: 0, zoom: 1 / d });
    B.draw();
    const gl = R.gl, bw = gl.drawingBufferWidth, bh = gl.drawingBufferHeight, px = new Uint8Array(bw * bh * 4);
    gl.readPixels(0, 0, bw, bh, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return { w: gl.drawingBufferWidth, h: gl.drawingBufferHeight, px: Array.from(px) };
  })()`);
  console.log(JSON.stringify(r));
} finally { await b.close(); }
""" % os.path.join(HERE, "play_cdp.mjs")


def png64(a):
    f = io.BytesIO()
    Image.fromarray(a.astype(np.uint8)).save(f, "PNG")
    return "data:image/png;base64," + base64.b64encode(f.getvalue()).decode()


def main():
    ap = argparse.ArgumentParser()
    for k in ("url", "shot", "ground", "file"):
        ap.add_argument(k)
    for k in ("index", "x", "y"):
        ap.add_argument(k, type=int)
    ap.add_argument("--dpr", default="1.25")
    a = ap.parse_args()
    meta = {e["index"]: e for e in json.load(open(os.path.join(ROOT, "extracted/sprites", a.file, "atlas.json")))["images"]}
    e = meta[a.index]
    T = np.asarray(Image.open(os.path.join(ROOT, "extracted/sprites", a.file, e["png"])).convert("RGBA")).astype(np.int32)
    h, w = T.shape[:2]
    pad = 4                                                   # a margin of ground around the picture
    x0, y0 = a.x - pad, a.y - pad
    W, H = w + 2 * pad, h + 2 * pad
    S = np.asarray(Image.open(oracle.shot(a.shot)).convert("RGB")).astype(np.int32)[y0:y0 + H, x0:x0 + W]
    G = np.asarray(Image.open(oracle.shot(a.ground)).convert("RGB")).astype(np.int32)[y0:y0 + H, x0:x0 + W]
    A = np.zeros((H, W), np.int32)
    A[pad:pad + h, pad:pad + w] = T[..., 3] >> 3
    m = A > 0
    print(f"ground: {int((np.abs(S - G).max(-1)[~m] > 0).sum())} px differ from SHOT around the picture (want 0)")
    # the exe's model
    I5 = np.zeros((H, W, 3), np.int32)
    I5[pad:pad + h, pad:pad + w] = T[..., :3] >> 3
    o5 = (A[..., None] * I5 + (31 - A[..., None]) * (G >> 3)) >> 5
    full = m & (A == 31)
    part = m & (A < 31)

    def rep(name, P5, only=None):
        d = np.abs(P5 - (S >> 3)).max(-1)
        for k, mm in (("opaque", full), ("partly transparent", part)):
            if only and k != only:
                continue
            n = int(mm.sum())
            print(f"  {name} {k}: {n} px, equal {int((d[mm] == 0).sum())}, 1 step {int((d[mm] == 1).sum())}, "
                  f"more {int((d[mm] > 1).sum())}")
    rep("exe model", o5)
    # play mode
    at = json.load(open(os.path.join(ROOT, "viewer/play/atlas", a.file + ".json")))
    pe = at["images"][str(a.index)]
    sheet = os.path.join(ROOT, "viewer/play/atlas", at["sheets"][pe[0]])
    g8 = ((G >> 3) << 3) | (G >> 5)
    inp = dict(w=W, h=H, ground=png64(np.dstack([g8, np.full((H, W), 255)])),
               sheet=png64(np.asarray(Image.open(sheet).convert("RGBA"))), sx=pe[1], sy=pe[2], sw=pe[3], sh=pe[4],
               flip=pe[7] is not None, px=pad, py=pad)
    with tempfile.TemporaryDirectory() as td:
        jp, mp = os.path.join(td, "in.json"), os.path.join(td, "run.mjs")
        json.dump(inp, open(jp, "w"))
        open(mp, "w").write(JS)
        out = subprocess.run(["node", mp, a.url, jp, a.dpr], capture_output=True, text=True, timeout=300)
    if out.returncode:
        raise SystemExit(out.stderr)
    r = json.loads(out.stdout.strip().splitlines()[-1])
    P = np.array(r["px"], np.int32).reshape(r["h"], r["w"], 4)[::-1][:H, :W, :3]   # readPixels rows bottom-up
    print(f"play mode (readPixels, {r['w']}x{r['h']} device px at dpr {a.dpr}):")
    rep("play mode", P >> 3)
    rep("play mode as floor(P / 8.25) (a blend of v << 3 | v >> 2 values)", (P * 4) // 33, "partly transparent")
    print(f"  play mode ground around the picture: {int((np.abs((P >> 3) - (G >> 3)).max(-1)[~m] > 0).sum())} px off")


if __name__ == "__main__":
    main()
