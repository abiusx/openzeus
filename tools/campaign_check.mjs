// Campaign screens in play mode, step by step (docs/play/campaign.md "Checks"): headless Chrome (tools/play_cdp.mjs:
// own profile, muted, dpr 1.25 by default) on your own server (a COPY of a campaign save, not a game in play), the
// interface at 80 % (one interface px = one device px at dpr 1.25). The steps run in the order given:
//   --js "CODE"            run in the page (an expression or statements; a returned promise is awaited)
//   --until "EXPR"         wait (up to 60 s) until EXPR is true in the page
//   --wait MS              sleep
//   --mouse X,Y            the mouse at interface px (hover looks)
//   --click X,Y            a left click there (uiDown + the button's release)
//   --grab X,Y,W,H OUT.ppm the drawn pixels of that rect (gl.readPixels after the next uiDraw) as a binary PPM
//   --shot OUT.png         a screenshot
//   --print "EXPR"         print EXPR's value (JSON)
// Compare a grab with the exe: python3 tools/screens_compare.py OUT.ppm re/oracle/runs/RUN/SHOT.bmp X,Y
//   node tools/campaign_check.mjs http://127.0.0.1:8781/play.html [--size 1280x800] [--dpr 1.25] [--pct 80]
//        [--leader NAME|none] STEPS...
import { launch } from "./play_cdp.mjs";
import { writeFileSync } from "node:fs";

const a = process.argv.slice(2), URL_ = a[0];
const opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
if (!URL_) { console.error("usage: node tools/campaign_check.mjs URL [--size WxH] [--dpr D] [--pct P] STEPS..."); process.exit(2); }
const [w, h] = opt("--size", "1280x800").split("x").map(Number);
const DPR = +opt("--dpr", 1.25), PCT = +opt("--pct", 80);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PAGE = `(() => {
  if (window.__sc) return true;
  const orig = window.uiDraw;
  window.__sc = { want: null };
  window.uiDraw = function (R) {
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
  window.__scClick = (x, y) => {
    const e = { button: 0, clientX: x * UIX.scale, clientY: y * UIX.scale, preventDefault() {}, stopPropagation() {} };
    UIX.mouse = [x, y];
    const r = uiDown(e);
    UIX.down = false; UIX.rep = null;
    return r;
  };
  return true;
})()`;

const LEADER = opt("--leader", "N");             // the stored leader name; "none": the first-open front end shows
const b = await launch({ width: w, height: h, dpr: DPR, leader: LEADER === "none" ? null : LEADER });
let code = 0;
try {
  await b.open(URL_);
  await b.waitFor("typeof UIX !== 'undefined' && UIX.D && typeof S !== 'undefined' && S && S.buildings && typeof P !== 'undefined' && P.f0 && window.ZText && window.ZInfo && ZInfo.ready()", 180000);
  await b.eval(PAGE);
  await b.eval(`uiSetSize(${PCT}, false); true`);
  await sleep(1500);
  for (let i = 1; i < a.length; i++) {
    const k = a[i];
    if (["--size", "--dpr", "--pct", "--leader"].includes(k)) { i++; continue; }
    if (k === "--js") { await b.eval(`(async () => { ${a[++i]} })().then(() => true)`); continue; }
    if (k === "--until") {
      const ex = a[++i], t0 = Date.now();
      while (!(await b.eval(`!!(${ex})`))) {
        if (Date.now() - t0 > 60000) { console.error(`timeout: ${ex}`); code = 1; break; }
        await sleep(200);
      }
      continue;
    }
    if (k === "--wait") { await sleep(+a[++i]); continue; }
    if (k === "--mouse") { const [x, y] = a[++i].split(",").map(Number); await b.eval(`UIX.mouse = [${x}, ${y}]; true`); continue; }
    if (k === "--click") { const [x, y] = a[++i].split(",").map(Number); await b.eval(`__scClick(${x}, ${y})`); await sleep(300); continue; }
    if (k === "--print") { console.log(JSON.stringify(await b.eval(a[++i]))); continue; }
    if (k === "--shot") { await b.shot(a[++i]); continue; }
    if (k === "--grab") {
      const [rx, ry, rw, rh] = a[++i].split(",").map(Number), out = a[++i];
      await sleep(400);
      const r = await b.eval(`__scGrab(${rx}, ${ry}, ${rw}, ${rh}).then(r => ({ s: r.s, px: r.px }))`);
      if (Math.abs(r.s - 1) > 1e-6) console.error(`warning: ${r.s} device px per interface px (not 1)`);
      writeFileSync(out, Buffer.concat([Buffer.from(`P6\n${rw} ${rh}\n255\n`), Buffer.from(r.px)]));
      continue;
    }
    console.error(`unknown step ${k}`); code = 2;
  }
  const errs = b.logs.filter(l => /EXC|rror/.test(l));
  if (errs.length) console.error(errs.slice(0, 10).join("\n"));
} finally {
  await b.close();
}
process.exit(code);
