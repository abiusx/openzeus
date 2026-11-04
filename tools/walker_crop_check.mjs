// Walker-window figure crops (exe FUN_00572FE0; play.js drawCrop; docs/play/info.md "Walker window"): read back,
// in headless Chrome at dpr 1.25 with the interface at 80 % (one interface px = one device px), a test figure's
// crop box and the map at its picture's top-left at 100 % (the same scale), with the figure and without it.
// Your own server on a COPY of a save (not a game in play):
//   python3 -m sim new COPY.pkl; python3 -m sim live COPY.pkl --port 8794 --speed 0 &
//   node tools/walker_crop_check.mjs http://127.0.0.1:8794/play.html OUTDIR --tile 160,160 --role cart --good fish \
//        --amount 100 --dir 0 [--win 68,32] [--view 0|2|4|6]
// Writes OUTDIR/{box,boxbare,map,mapbare}.ppm (box 52x52 at the window's first RIMS box; map 48x48 at the anchor)
// and OUTDIR/info.json; compare with tools/walker_crop_compare.py. The figure is put into the frames (P.f0/P.f1) as
// id 999999 standing at the tile, world heading --dir (0 = N, picture NE in view 0); a second test walker 999998
// stands next to it (--other ROLE) to check that other figures are left out of the crop.
import { launch } from "./play_cdp.mjs";
import { writeFileSync, mkdirSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [URL_, OUT] = a;
if (!URL_ || !OUT) { console.error("usage: node tools/walker_crop_check.mjs URL OUTDIR --tile X,Y --role R [--good G] [--amount N] [--dir D] [--win X,Y] [--other ROLE]"); process.exit(2); }
mkdirSync(OUT, { recursive: true });
const [tx, ty] = opt("--tile", "160,160").split(",").map(Number);
const [wx, wy] = opt("--win", "68,32").split(",").map(Number);
const role = opt("--role", "cart"), good = opt("--good", "fish"), amount = +opt("--amount", 100), dir = +opt("--dir", 0);
const other = opt("--other", ""), view = +opt("--view", 0);

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
const ppm = (f, w, h, px) => writeFileSync(f, Buffer.concat([Buffer.from(`P6\n${w} ${h}\n255\n`), Buffer.from(px)]));
try {
  await b.open(URL_);
  await b.waitFor("typeof UIX !== 'undefined' && UIX.D && typeof S !== 'undefined' && S && T && P.f0 && window.ZInfo && ZInfo.ready() && objBatch && objBatch.n > 0", 180000);
  await b.eval(`uiSetSize(80, false); P.playing && togglePlay(); true`);
  await b.eval(`(() => {
    window.__wc = { on: true, want: null };
    const put = f => {
      if (!f) return;
      f.walkers = f.walkers.filter(w => w[0] !== 999999 && w[0] !== 999998);
      if (__wc.on) f.walkers.push([999999, ${tx}, ${ty}, ${JSON.stringify(role)}, ${JSON.stringify(good)}, ${amount}, 0, 0, null]);
      if (${JSON.stringify(other)}) f.walkers.push([999998, ${tx + 1}, ${ty}, ${JSON.stringify(other)}, null, 0, 0, 0, null]);
    };
    const orig = window.drawFrame;
    window.drawFrame = function () { put(P.f0); put(P.f1); lastDir[999999] = ${dir}; lastDir[999998] = 4; orig(); };
    const ui = window.uiDraw;
    window.uiDraw = function (R) {
      ui(R);
      const q = __wc.want;
      if (!q) return;
      __wc.want = null;
      const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const s = UIX.scale * devicePixelRatio, res = {};
      for (const [k, [rx, ry, rw, rh]] of Object.entries(q.rects)) {
        const o = [];
        for (let y = 0; y < rh; y++) for (let x = 0; x < rw; x++) {
          const X = Math.round((rx + x) * s), Y = H - 1 - Math.round((ry + y) * s), i = (Y * W + X) * 4;
          o.push(px[i], px[i + 1], px[i + 2]);
        }
        res[k] = o;
      }
      q.res({ s, res });
    };
    return true;
  })()`);
  if (view) { await b.eval(`while (VIEW !== ${view}) rotateView(2); true`); await new Promise(r => setTimeout(r, 1500)); }
  // the map at the crop's scale (one picture px = one interface px), the figure at screen (300, 560) (under no window)
  await b.eval(`clampCam = () => {}; cam.zoom = UIX.scale; cam.x = tileX(${tx}, ${ty}) + 29 - 300; cam.y = tileY(${tx}, ${ty}) + 15 - 560; true`);
  await new Promise(r => setTimeout(r, 2000));
  await b.eval(`openWalkers(${tx}, ${ty}, 999999, ${wx - 12}, ${wy + 40}); UIX.info.x = ${wx}; UIX.info.y = ${wy}; true`);
  await new Promise(r => setTimeout(r, 2500));
  const grab = async () => b.eval(`(() => {
    const a = Scene.walkerAnchor(999999) || cropLast.get(999999), o = cropOrigin(999999);
    const mx = o[0] - cam.x, my = o[1] - cam.y;   // the crop's origin on screen (interface px: zoom = UIX.scale)
    return new Promise(res => { __wc.want = { rects: { box: [${wx + 25}, ${wy + 45}, 52, 52], map: [mx, my, 48, 48] }, res }; })
      .then(r => ({ s: r.s, res: r.res, anchor: a, origin: o, map: [mx, my] }));
  })()`);
  const r1 = await grab();
  await b.eval(`__wc.on = false; true`);
  await new Promise(r => setTimeout(r, 1500));
  const r2 = await grab();
  ppm(`${OUT}/box.ppm`, 52, 52, r1.res.box); ppm(`${OUT}/map.ppm`, 48, 48, r1.res.map);
  ppm(`${OUT}/boxbare.ppm`, 52, 52, r2.res.box); ppm(`${OUT}/mapbare.ppm`, 48, 48, r2.res.map);
  const info = { scale: r1.s, anchor: r1.anchor, origin: r1.origin, map: r1.map, tile: [tx, ty], role, good, amount, dir, win: [wx, wy] };
  writeFileSync(`${OUT}/info.json`, JSON.stringify(info));
  await b.shot(`${OUT}/screen.png`);
  const errs = b.logs.filter(l => /EXC|rror/.test(l));
  if (errs.length) console.error(errs.slice(0, 10).join("\n"));
  console.log(JSON.stringify(info));
} finally { await b.close(); }
