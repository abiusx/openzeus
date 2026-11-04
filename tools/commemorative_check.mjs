// Play-mode shots of every commemorative monument in the 4 views (tools/commemorative_check.py has the steps).
// Headless Chrome (tools/play_cdp.mjs: own profile, muted, dpr 1.25) on your own server with the prepared COPY:
//   node tools/commemorative_check.mjs http://127.0.0.1:PORT/play.html LAYOUT.json DIR [--views 0,2,4,6] [--only V,V]
// Original sprites as PNG (?tex=png; a fresh profile has no hi-res set chosen), zoom 1/dpr (one world px = one device px), the city
// paused; each shot centred on the monument: DIR/vNN_viewK.png. Also DIR/menu22.png: the Monuments submenu open.
import { launch } from "./play_cdp.mjs";
import { mkdirSync, readFileSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [URL_, LAYOUT, DIR] = a;
if (!URL_ || !LAYOUT || !DIR) { console.error("usage: node tools/commemorative_check.mjs URL LAYOUT.json DIR [--views 0,2,4,6] [--only V,..]"); process.exit(2); }
const VIEWS = opt("--views", "0,2,4,6").split(",").map(Number);
const ONLY = opt("--only", null);
const L = JSON.parse(readFileSync(LAYOUT, "utf8")).filter(r => !ONLY || ONLY.split(",").map(Number).includes(r[0]));
mkdirSync(DIR, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PAGE = String.raw`
window.CC = {
  setView(v) { let n = 0; while (VIEW !== v && n++ < 4) rotateView(2); return VIEW; },
  centre(x, y) {                                   // the tile's centre in the middle of the map area (no edge clamp)
    clampCam = () => {};
    cam.zoom = 1 / devicePixelRatio;
    const e = (T.elev[y * N + x] || 0) * 30;
    cam.x = tileX(x, y) + 29 - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
    cam.y = tileY(x, y) + 15 - e - innerHeight / 2 / cam.zoom;
    cam.x = Math.round(cam.x); cam.y = Math.round(cam.y);   // whole device px: no resampling of the pictures
    return [cam.x, cam.y];
  },
};
true`;

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
try {
  await b.open(URL_ + (URL_.includes("?") ? "&" : "?") + "tex=png");   // exact original sprites (default: compressed)
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && window.Order && objBatch && objBatch.n > 0", 180000);
  await b.eval(PAGE);
  await b.eval("P.playing && togglePlay(), 0");
  await sleep(1500);
  for (const v of VIEWS) {
    await b.eval(`CC.setView(${v})`);
    await sleep(1500);                              // turned terrain rebuilt
    for (const [vv, x, y, n] of L) {
      const c = Math.floor((n - 1) / 2);
      await b.eval(`CC.centre(${x + c}, ${y + c})`);
      await sleep(250);
      await b.shot(`${DIR}/v${String(vv).padStart(2, "0")}_view${v}.png`);
    }
  }
  await b.eval("CC.setView(0); UIX.page = 9; UIX.submenu = 22; 0");   // Aesthetics page, Monuments submenu
  await sleep(500);
  await b.shot(`${DIR}/menu22.png`);
  console.log(`${L.length} monuments x ${VIEWS.length} views -> ${DIR}`);
} finally { await b.close(); }
