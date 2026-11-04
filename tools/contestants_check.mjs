// Play-mode check of the games contestants (figure 0x38, tools/play_contestants.py) in the 4 views.
// Headless Chrome (tools/play_cdp.mjs: own profile, muted, dpr 1.25) on your own server with a prepared COPY
// whose contestants are on the map (docs/logic/games.md "Ours"):
//   python3 -m sim live COPY.pkl --port PORT --speed 0 &        (your own port, not a game in play)
//   node tools/contestants_check.mjs http://127.0.0.1:PORT/play.html DIR [--views 0,2,4,6]
// For each view: plays a few seconds and records every drawn contestant picture (WALKER_HITS: role by good ->
// atlas index), checks index = walk start + 8 * frame + dir of the resolved role (frame 0..11, dir = heading minus view), counts the hidden
// (waiting) ones that were drawn (must be 0), then pauses, centres on a walking contestant and shoots DIR/viewK.png.
import { launch } from "./play_cdp.mjs";
import { mkdirSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [URL_, DIR] = a;
if (!URL_ || !DIR) { console.error("usage: node tools/contestants_check.mjs URL DIR [--views 0,2,4,6]"); process.exit(2); }
const VIEWS = opt("--views", "0,2,4,6").split(",").map(Number);
mkdirSync(DIR, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PAGE = String.raw`
window.CT = {
  seen: {}, bad: [], hiddenDrawn: 0,
  setView(v) { let n = 0; while (VIEW !== v && n++ < 4) rotateView(2); return VIEW; },
  sample() {                                        // the contestants drawn in the last frame
    const recs = new Map(P.f0.walkers.filter(w => w[3] === "contestant").map(w => [w[0], w]));
    for (const h of WALKER_HITS) {
      const w = recs.get(h[0]);
      if (!w) continue;
      if (w[7] && w[7][0] === "hidden") { this.hiddenDrawn++; continue; }
      const m = roleOf(MAP.walkers.roles, "contestant", w[4]), rel = h[9] - m.walk.start;
      if (lastDir[h[0]] != null && rel % 8 !== viewDir(lastDir[h[0]])) this.bad.push([h[0], w[4], h[9], "dir"]);
      const key = w[4] + ":" + h[8];
      (this.seen[key] = this.seen[key] || new Set()).add(rel);
      if (!(rel >= 0 && rel < 96)) this.bad.push([h[0], w[4], h[9]]);
    }
    return recs.size;
  },
  report() { const o = {}; for (const k in this.seen) o[k] = [...this.seen[k]].sort((a, b) => a - b); return o; },
  centre() {                                        // a walking contestant in the middle of the map area
    const w = P.f0.walkers.find(w => w[3] === "contestant" && !(w[7] && w[7][0] === "hidden"));
    if (!w) return null;
    clampCam = () => {};
    cam.zoom = 2 / devicePixelRatio;
    cam.x = Math.round(tileX(w[1], w[2]) + 29 - (UIX.panelX * UIX.scale) / 2 / cam.zoom);
    cam.y = Math.round(tileY(w[1], w[2]) + 15 - (T.elev[w[2] * N + w[1]] || 0) * 30 - innerHeight / 2 / cam.zoom);
    return [w[0], w[1], w[2], w[4]];
  },
  total() { return P.f0.walkers.filter(w => w[3] === "contestant").length; },
  hidden() { return P.f0.walkers.filter(w => w[3] === "contestant" && w[7] && w[7][0] === "hidden").length; },
};
true`;

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
try {
  await b.open(URL_ + (URL_.includes("?") ? "&" : "?") + "tex=png");
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && window.Order && objBatch && objBatch.n > 0", 180000);
  await b.eval(PAGE);
  console.log("contestants in the frame:", await b.eval("CT.total()"), "hidden:", await b.eval("CT.hidden()"));
  for (const v of VIEWS) {
    await b.eval("P.playing && togglePlay(), 0");
    await b.eval(`CT.setView(${v})`);
    await sleep(1500);
    const at = await b.eval("JSON.stringify(CT.centre())");
    await b.eval("P.playing || togglePlay(), 0");
    for (let i = 0; i < 30; i++) { await sleep(100); await b.eval("CT.sample()"); }
    await b.eval("P.playing && togglePlay(), 0");
    await b.eval("JSON.stringify(CT.centre())");
    await sleep(400);
    await b.shot(`${DIR}/view${v}.png`);
    console.log(`view ${v}: centred on ${at}`);
  }
  console.log("drawn (good:file -> walk index - start):", await b.eval("JSON.stringify(CT.report())"));
  console.log("out of the walk block:", await b.eval("JSON.stringify(CT.bad)"), "hidden drawn:", await b.eval("CT.hiddenDrawn"));
} finally { await b.close(); }
