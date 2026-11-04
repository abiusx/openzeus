// City-view panel edge check (bugs.md 267, docs/play/ui.md 1): headless muted Chrome (tools/play_cdp.mjs) on a
// running server; for each window size x UI size (x sharp on/off) it reads the drawn pixels back right after uiDraw
// (gl.readPixels, same frame) and checks:
//   - the panel's right edge ((panelX + 186) x scale) lies inside the window, the canvas is window x dpr, no page scroll;
//   - nothing of the map shows at x >= panelX: the frame is read twice, the second time with the map layer replaced
//     by a magenta clear (drawFrame swapped; the UI must not change); every differing pixel right of the panel's first
//     device column counts (a hole in the panel or a gap right of it shows the map); pixels that change between two
//     plain frames (animated minimap dots) are left out;
//   - the columns panelX - 1, panelX, the panel's last column and the window's last column: black (0,0,0) pixels
//     (a hole or an unpainted strip shows as black on the cleared canvas).
// Usage (your own server on a COPY of a save, not a game in play):
//   python3 -m sim live /tmp/copy.pkl --port 8794 --speed 0 &
//   node tools/panel_edge_check.mjs http://127.0.0.1:8794/play.html [--sizes 1280x800,...] [--pcts 100,150,200]
//        [--dpr 1.25] [--shots DIR]
import { launch } from "./play_cdp.mjs";
import { mkdirSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const URL_ = a[0];
if (!URL_ || URL_.startsWith("--")) { console.error("usage: node tools/panel_edge_check.mjs URL [--sizes WxH,...] [--pcts P,...] [--dpr D] [--shots DIR]"); process.exit(2); }
const SIZES = opt("--sizes", "1280x800,1366x768,1440x900,1000x700,800x600,640x480,500x400,1920x1080").split(",").map(s => s.split("x").map(Number));
const PCTS = opt("--pcts", "100,125,150,175,200").split(",").map(Number);
const DPR = +opt("--dpr", 1.25), SHOTS = opt("--shots", null);
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const PAGE = `(() => {
  if (window.__pec) return true;
  const orig = window.uiDraw;
  window.__pec = { want: null };
  window.uiDraw = function (R) {
    orig(R);
    const q = window.__pec.want;
    if (q) {
      const gl = R.gl, w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(w * h * 4);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
      window.__pec.want = null; q.res({ w, h, px });
    }
  };
  const grab = () => new Promise(res => { window.__pec.want = { res }; });
  window.__pecRun = async () => {
    const A = await grab(), keep = window.drawFrame;
    window.drawFrame = () => { const gl = R.gl; gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight); gl.clearColor(1, 0, 1, 1); gl.clear(gl.COLOR_BUFFER_BIT); };
    let B; try { B = await grab(); } finally { window.drawFrame = keep; }
    const A2 = await grab();                         // animated panel parts (minimap dots) differ between A and A2: not counted
    const s = UIX.scale * devicePixelRatio, pX = Math.round(UIX.panelX * s), pR = Math.round((UIX.panelX + 186) * s) - 1;
    let diff = 0; const cols = {};
    for (let y = 0; y < A.h; y++) for (let x = pX + 1; x < A.w; x++) {
      const i = (y * A.w + x) * 4;
      if (A.px[i] !== A2.px[i] || A.px[i + 1] !== A2.px[i + 1] || A.px[i + 2] !== A2.px[i + 2]) continue;
      if (A.px[i] !== B.px[i] || A.px[i + 1] !== B.px[i + 1] || A.px[i + 2] !== B.px[i + 2]) {
        diff++; const c = cols[x] || (cols[x] = [0, A.h - 1 - y, A.h - 1 - y]); c[0]++; c[1] = Math.min(c[1], A.h - 1 - y); c[2] = Math.max(c[2], A.h - 1 - y); }
    }
    const where = Object.entries(cols).sort((p, q) => q[1][0] - p[1][0]).slice(0, 4).map(([x, c]) => [+x, ...c]);   // [device x, n, top row, bottom row]
    const rows = Math.min(A.h, Math.round(UIX.H * s));
    const black = x => { if (x < 0 || x >= A.w) return -1; let n = 0;
      for (let y = A.h - rows; y < A.h; y++) { const i = (y * A.w + x) * 4; if (!A.px[i] && !A.px[i + 1] && !A.px[i + 2]) n++; } return n; };
    return { w: A.w, h: A.h, pX, pR, diff, where, bLeft: black(pX - 1), bPanel: black(pX), bPanelR: black(Math.min(pR, A.w - 1)), bRight: black(A.w - 1) };
  };
  return true;
})()`;

let bad = 0;
for (const [w, h] of SIZES) {
  const b = await launch({ width: w, height: h, dpr: DPR });
  try {
    await b.open(URL_);
    await b.waitFor("typeof UIX !== 'undefined' && UIX.D && typeof S !== 'undefined' && S && S.buildings && window.ZText", 180000);
    await b.eval(PAGE);
    await new Promise(r => setTimeout(r, 1500));
    for (const pct of PCTS) for (const sharp of [false, true]) {
      await b.eval(`uiSetSize(${pct}, ${sharp}); true`);
      await new Promise(r => setTimeout(r, 300));
      const lay = await b.eval(`({ W: UIX.W, H: UIX.H, panelX: UIX.panelX, scale: +UIX.scale.toFixed(4), iw: innerWidth, ih: innerHeight,
        cw: document.getElementById('view').width, sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight })`);
      const r = await b.eval("__pecRun()");
      const right = +((lay.panelX + 186) * lay.scale).toFixed(2);
      const res = { size: `${w}x${h}`, pct, sharp, ...lay, panelRightCss: right, ...r };
      const fail = right > lay.iw + 0.01 || lay.sw > lay.iw || lay.sh > lay.ih || r.pR >= r.w || r.diff || r.bPanel || r.bPanelR || r.bRight;
      if (fail) bad++;
      console.log((fail ? "BAD " : "ok  ") + JSON.stringify(res));
      if (SHOTS) await b.shot(`${SHOTS}/pe-${w}x${h}-${pct}${sharp ? "s" : ""}.png`);
    }
  } finally { await b.close(); }
}
console.log(bad ? `FAIL ${bad}` : "OK");
process.exit(bad ? 1 : 0);
