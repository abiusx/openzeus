// In-game screen pixel check (docs/play/screens.md "Checks"): headless Chrome (tools/play_cdp.mjs: own profile,
// muted, dpr 1.25) on your own server (a COPY of a save, not a game in play). The interface is set to 80 %
// so one interface pixel is one device pixel (dpr 1.25 x 0.8); a screen is opened by --open JS (run once) and fed
// by --each JS (run in the page before every frame is drawn, e.g. to put the oracle's numbers into a building
// record); the pixels of --rect X,Y,W,H (interface px) are read back with gl.readPixels right after that frame's
// uiDraw and written as a binary PPM. Compare with the exe: tools/screens_compare.py.
//   python3 -m sim live COPY.pkl --port 8781 --speed 0 &
//   node tools/screens_check.mjs http://127.0.0.1:8781/play.html OUT.ppm --rect 68,96,464,496 \
//        --open "..." --each "..." [--size 1280x800] [--dpr 1.25] [--pct 80] [--shot OUT.png] [--mouse X,Y]
import { launch } from "./play_cdp.mjs";
import { writeFileSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [URL_, OUT] = a;
if (!URL_ || !OUT) { console.error("usage: node tools/screens_check.mjs URL OUT.ppm --rect X,Y,W,H [--open JS] [--each JS] [--size WxH] [--dpr D] [--pct P] [--shot PNG] [--mouse X,Y]"); process.exit(2); }
const [w, h] = opt("--size", "1280x800").split("x").map(Number);
const DPR = +opt("--dpr", 1.25), PCT = +opt("--pct", 80);
const [rx, ry, rw, rh] = opt("--rect", "0,0,100,100").split(",").map(Number);
const MOUSE = opt("--mouse", null);

const PAGE = `(() => {
  if (window.__sc) return true;
  const orig = window.uiDraw;
  window.__sc = { want: null, each: null };
  window.uiDraw = function (R) {
    if (window.__sc.each) { try { window.__sc.each(); } catch (e) { console.error("each: " + e); } }
    orig(R);
    const q = window.__sc.want;
    if (q) {
      const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
      window.__sc.want = null;
      const s = UIX.scale * devicePixelRatio, out = [];
      for (let y = 0; y < q.rh; y++) for (let x = 0; x < q.rw; x++) {
        const X = Math.round((q.rx + x) * s), Y = H - 1 - Math.round((q.ry + y) * s), i = (Y * W + X) * 4;
        out.push(px[i], px[i + 1], px[i + 2]);
      }
      q.res({ s, px: out });
    }
  };
  window.__scGrab = (rx, ry, rw, rh) => new Promise(res => { window.__sc.want = { rx, ry, rw, rh, res }; });
  return true;
})()`;

const b = await launch({ width: w, height: h, dpr: DPR });
try {
  await b.open(URL_);
  await b.waitFor("typeof UIX !== 'undefined' && UIX.D && typeof S !== 'undefined' && S && S.buildings && typeof P !== 'undefined' && P.f0 && window.ZText && window.ZInfo && ZInfo.ready()", 180000);
  await b.eval(PAGE);
  await b.eval(`uiSetSize(${PCT}, false); true`);
  if (opt("--each")) await b.eval(`window.__sc.each = () => { ${opt("--each")} }; true`);
  if (opt("--open")) await b.eval(`(() => { ${opt("--open")} })(); true`);
  if (MOUSE) { const [mx, my] = MOUSE.split(",").map(Number); await b.eval(`UIX.mouse = [${mx}, ${my}]; true`); }
  await new Promise(r => setTimeout(r, 2500));                      // sprites and fonts load
  const r = await b.eval(`__scGrab(${rx}, ${ry}, ${rw}, ${rh}).then(r => ({ s: r.s, px: r.px }))`);
  if (Math.abs(r.s - 1) > 1e-6) console.error(`warning: ${r.s} device px per interface px (not 1)`);
  writeFileSync(OUT, Buffer.concat([Buffer.from(`P6\n${rw} ${rh}\n255\n`), Buffer.from(r.px)]));
  if (opt("--shot")) await b.shot(opt("--shot"));
  const errs = b.logs.filter(l => /EXC|rror/.test(l));
  if (errs.length) console.error(errs.slice(0, 10).join("\n"));
  console.log(JSON.stringify({ out: OUT, rect: [rx, ry, rw, rh], scale: r.s, errors: errs.length }));
} finally { await b.close(); }
