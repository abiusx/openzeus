// World map screen check (docs/play/world.md "Checked", bugs.md 180): headless Chrome (tools/play_cdp.mjs: own
// profile, muted) on a running server; for each window size and UI size it opens the world map, selects a city
// and reads the drawn pixels back right after uiDraw (same frame):
//   - layout: canvas = window x dpr, panel at uiPanelX (60-px view columns), its right edge inside the window, no page scroll;
//   - the map layer (routes, cities, labels, armies) leaves the side panel and the top bar untouched: the frame is
//     read once as is and once with the layer emptied; every pixel at x >= panelX or y < 30 must be equal;
//   - the same at every zoom (--zooms, x fit; ours) and scroll corner (the picture must not cover the top bar);
//   - at zoom 1 (fit) the whole picture lies inside the map area; a click on each visible city's centre selects it;
//   - the panel/map boundary columns (panelX - 1, panelX) and the right-most column, as RGB runs;
//   - WorldMap.overflow (panel text wider than its box).
// Usage (your own server on a COPY of a save, not a game in play):
//   python3 -m sim live /tmp/copy.pkl --port 8823 --speed 0 &
//   node tools/world_map_check.mjs http://127.0.0.1:8823/play.html [--city Corinth] [--shots DIR]
//        [--sizes 1280x800,1600x1000,1920x1080,2560x1300] [--pcts 100,175,200] [--zooms 1,2,4] [--dpr 1.25]
import { launch } from "./play_cdp.mjs";
import { mkdirSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const URL_ = a[0];
if (!URL_ || URL_.startsWith("--")) { console.error("usage: node tools/world_map_check.mjs URL [--city NAME] [--shots DIR] [--sizes WxH,...] [--pcts P,...] [--dpr D]"); process.exit(2); }
const SIZES = opt("--sizes", "1280x800,1600x1000,1920x1080,2560x1300").split(",").map(s => s.split("x").map(Number));
const PCTS = opt("--pcts", "100,175,200").split(",").map(Number);
const ZOOMS = opt("--zooms", "1,2,4").split(",").map(Number);
const DPR = +opt("--dpr", 1.25), CITY = opt("--city", "Corinth"), SHOTS = opt("--shots", null);
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

// in the page: grab(empty) resolves with the frame's pixels after the next uiDraw (map layer emptied or not)
const PAGE = `(() => {
  if (window.__wmc) return true;
  const orig = window.uiDraw;
  window.__wmc = { want: null };
  window.uiDraw = function (R) {
    const q = window.__wmc.want, W = WorldMap.data;
    let keep = null;
    if (q && q.empty && W) { keep = [W.cities.map(c => c.shown), W.routes, W.armies]; W.cities.forEach(c => { c.shown = false; }); W.routes = []; W.armies = []; }
    orig(R);
    if (keep) { W.cities.forEach((c, i) => { c.shown = keep[0][i]; }); W.routes = keep[1]; W.armies = keep[2]; }
    if (q) {
      const gl = R.gl, w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(w * h * 4);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
      window.__wmc.want = null; q.res({ w, h, px });
    }
  };
  window.__wmcGrab = empty => new Promise(res => { window.__wmc.want = { empty, res }; });
  window.__wmcCompare = async () => {
    const A = await __wmcGrab(false), B = await __wmcGrab(true);
    const s = UIX.scale * devicePixelRatio, pX = Math.round(UIX.panelX * s), top = Math.floor(30 * s);
    let panel = 0, bar = 0, map = 0;
    for (let y = 0; y < A.h; y++) for (let x = 0; x < A.w; x++) {
      const i = (y * A.w + x) * 4;
      if (A.px[i] === B.px[i] && A.px[i + 1] === B.px[i + 1] && A.px[i + 2] === B.px[i + 2]) continue;
      const yt = A.h - 1 - y;                        // readPixels rows are bottom-up; rows wholly above y 30 (a row that straddles it at dpr 1.25 belongs to neither)
      if (x >= pX) panel++; else if (yt < top) bar++; else map++;
    }
    const col = x => { const runs = []; for (let y = A.h - 1; y >= 0; y--) { const i = (y * A.w + x) * 4, k = A.px[i] + "," + A.px[i + 1] + "," + A.px[i + 2];
      if (runs.length && runs[runs.length - 1][0] === k) runs[runs.length - 1][1]++; else runs.push([k, 1]); } return runs; };
    const black = x => col(x).filter(r => r[0] === "0,0,0").reduce((t, r) => t + r[1], 0);
    let barHash = 0;                                 // the top bar's bottom edge (UI rows 24..29, static art): must not change with scroll/zoom
    for (let y = A.h - top; y < A.h - Math.round(24 * s); y++) for (let x = 0; x < pX; x++) { const i = (y * A.w + x) * 4; barHash = (barHash * 31 + A.px[i] * 7 + A.px[i + 1] * 3 + A.px[i + 2]) >>> 0; }
    return { panel, bar, map, barHash, pX, w: A.w, h: A.h, blackLeft: black(pX - 1), blackPanel: black(pX), blackRight: black(A.w - 1),
             colPanel: col(pX).length, colRight: col(A.w - 1).length };
  };
  return true;
})()`;

let bad = 0;
for (const [w, h] of SIZES) {
  const b = await launch({ width: w, height: h, dpr: DPR });
  try {
    await b.open(URL_);
    await b.waitFor("typeof UIX !== 'undefined' && UIX.D && window.WorldMap && typeof S !== 'undefined' && S && S.buildings && window.ZText", 180000);
    await b.eval(PAGE);
    for (const pct of PCTS) {
      await b.eval(`uiSetSize(${pct}, false); WorldMap.isOpen() || WorldMap.toggle(); true`);
      await b.waitFor("WorldMap.conf && WorldMap.data && WorldMap.data.cities");
      await b.eval(`(() => { const c = WorldMap.data.cities.find(c => c.name === ${JSON.stringify(CITY)}); WorldMap.select(c ? c.id : null); return true; })()`);
      await new Promise(r => setTimeout(r, 1500));               // the picture loads
      const lay = await b.eval(`({ W: UIX.W, H: UIX.H, panelX: UIX.panelX, scale: UIX.scale, iw: innerWidth, ih: innerHeight,
        cw: document.getElementById('view').width, ch: document.getElementById('view').height,
        sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight, view: WorldMap.view && WorldMap.view() })`);
      const panelRight = (lay.panelX + 186) * lay.scale;
      const res = { size: `${w}x${h}`, pct, ...lay, panelRightCss: +panelRight.toFixed(2), corners: [] };
      for (const z of ZOOMS) for (const [sx, sy] of [[0, 0], [1e4, 0], [0, 1e4], [1e4, 1e4]]) {
        await b.eval(`(() => { WorldMap.zoom = ${z}; WorldMap.view(); WorldMap.scroll[0] = ${sx}; WorldMap.scroll[1] = ${sy}; return true; })()`);
        const r = await b.eval("__wmcCompare()");
        // fit (zoom 1): the whole picture inside the map area; hit-test: a click on each visible city's centre selects it
        const g = await b.eval(`(() => { const v = WorldMap.view(), out = { k: +v.k.toFixed(3), zoom: WorldMap.zoom, ox: v.ox, oy: v.oy,
            whole: v.ox >= 0 && v.oy >= 30 && v.ox + v.pw * v.k <= v.vw + 0.5 && v.oy + v.ph * v.k <= 30 + v.vh + 0.5, hits: 0, misses: [] };
          const keep = WorldMap.selected;
          for (const c of WorldMap.data.cities) { if (!c.map || !c.shown) continue;
            const x = v.ox + c.map.x * v.k, y = v.oy + c.map.y * v.k;
            if (x < 0 || x >= v.vw || y < 30 || y >= UIX.H) continue;
            WorldMap.down({ button: 0 }, x, y);
            if (WorldMap.selected === c.id) out.hits++; else out.misses.push(c.name); }
          WorldMap.select(keep); return out; })()`);
        Object.assign(r, g);
        r.scroll = await b.eval("WorldMap.scroll.map(Math.round)");
        r.overflow = (await b.eval("WorldMap.overflow.length"));
        res.corners.push(r);
        if (r.panel || r.bar || r.barHash !== res.corners[0].barHash || r.misses.length || (z === 1 && !r.whole)) bad++;
        if (SHOTS) await b.shot(`${SHOTS}/wm-${w}x${h}-${pct}-z${z}-${r.scroll.join("_")}.png`);
      }
      if (panelRight > lay.iw + 0.01 || lay.sw > lay.iw || lay.sh > lay.ih) bad++;
      console.log(JSON.stringify(res));
    }
  } finally { await b.close(); }
}
console.log(bad ? `FAIL ${bad}` : "OK");
process.exit(bad ? 1 : 0);
