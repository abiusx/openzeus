// Ground under monument step tiles (TODO 11-02, bugs.md 400; docs/play/monuments.md 3). The exe's image grid holds only
// the step picture on an extras tile (terrain 0x10000000) that gets one: FUN_00521520 writes it there and
// map_tiles_update_images 0x0051F450 skips such a tile, so no ground is computed under it. Play mode leaves those
// tiles out of the terrain batch (scene.js stepGround, play.js buildTerrain), as the exe. This check draws the frame
// that way and again with the computed ground under the steps (stepGround emptied, ours before 11-02), and reads
// both back with gl.readPixels right after the page's frame, at dpr 1.25: a pixel that changes is one where the
// ground would show through (a step picture's translucent pixels, or no step picture over it). A third grab (ground back) leaves out pixels that change on their own (fire pots, priestesses,
// walkers). For every monument of the save, views 0/2/4/6, zoom 100 % and 200 %. YOUR OWN server on a save copy.
//
//   node tools/step_ground_check.mjs http://127.0.0.1:8841/play.html [--shot DIR]
import { launch } from "./play_cdp.mjs";

const URL_ = process.argv[2];
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const SHOT = opt("--shot", null);

const PAGE = `(() => {
  if (window.__sg) return true;
  const orig = window.uiDraw;
  window.__sg = { want: null };
  window.uiDraw = function (R) {
    orig(R);
    const q = window.__sg.want;
    if (q) {
      const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
      window.__sg.want = null;
      q.res({ W, H, px });
    }
  };
  window.__sgGrab = () => new Promise(res => { window.__sg.want = { res }; });
  const wait = ms => new Promise(r => setTimeout(r, ms));
  window.__sgRun = async (bi, view, zoom) => {
    const b = S.buildings[bi];
    while (VIEW !== view) rotateView(2);
    await wait(300);
    const tiles = Monuments.stepTiles(b, MCTX, N);
    if (!tiles.length) return { steps: 0 };
    const cx = b.x + (b.w || 1) / 2, cy = b.y + (b.h || 1) / 2;
    cam.zoom = zoom;
    const ax = Math.round(cx), ay = Math.round(cy);
    cam.x = tileX(ax, ay) - (UIX.panelX * UIX.scale) / 2 / cam.zoom; cam.y = tileY(ax, ay) - innerHeight / 2 / cam.zoom;
    await wait(600);
    const a = await __sgGrab();                          // as the exe: no ground under the step tiles (play.js)
    const sg = window.stepGround;
    window.stepGround = () => new Set();                 // the ground drawn under them (ours before 11-02)
    buildTerrain(); await wait(200);
    const bb = await __sgGrab();
    window.stepGround = sg;
    buildTerrain(); await wait(200);
    const c = await __sgGrab();
    // only the ground pictures' rectangles of the step tiles (buildTerrain: 58 x 30 at tileX, tileY - 30 elev, the
    // tile's left corner in this view): elsewhere nothing changes but animations
    const sc = cam.zoom * devicePixelRatio, W = a.W, H = a.H, panel = Math.floor(UIX.panelX * UIX.scale * devicePixelRatio);
    const inRect = new Uint8Array(W * H);
    for (const t of tiles) {
      const x = t % N, y = Math.floor(t / N), px = tileX(x, y), py = tileY(x, y) - T.elev[t] * 30;
      const x0 = Math.max(0, Math.floor((px - cam.x) * sc)), x1 = Math.min(panel, Math.ceil((px + 58 - cam.x) * sc));
      const y0 = Math.max(0, Math.floor((py - cam.y) * sc)), y1 = Math.min(H, Math.ceil((py + 30 - cam.y) * sc));
      for (let yy = y0; yy < y1; yy++) for (let xx = x0; xx < x1; xx++) inRect[(H - 1 - yy) * W + xx] = 1;
    }
    let changed = 0, live = 0, sample = null;
    for (let y = 0; y < H; y++) for (let x = 0; x < Math.min(W, panel); x++) {
      if (!inRect[y * W + x]) continue;
      const i = (y * W + x) * 4;
      const ab = a.px[i] !== bb.px[i] || a.px[i + 1] !== bb.px[i + 1] || a.px[i + 2] !== bb.px[i + 2];
      if (!ab) continue;
      const ac = a.px[i] !== c.px[i] || a.px[i + 1] !== c.px[i + 1] || a.px[i + 2] !== c.px[i + 2];
      if (ac) { live++; continue; }
      changed++;
      if (!sample) sample = [x, H - 1 - y, [...a.px.slice(i, i + 3)], [...bb.px.slice(i, i + 3)]];
    }
    return { key: b.key, at: [b.x, b.y], steps: tiles.length, changed, live, sample };
  };
  return true;
})()`;

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
let fails = 0, runs = 0;
try {
  await b.open(URL_);
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && window.Monuments && objBatch && objBatch.n > 0", 180000);
  await b.eval("P.playing && togglePlay(), setMuted(true), 0");
  await b.eval(PAGE);
  const mons = await b.eval("S.buildings.map((b, i) => b.kind === 'monument' && b.pieces ? [i, b.key] : null).filter(Boolean)");
  for (const [bi, key] of mons) {
    for (const view of [0, 2, 4, 6]) for (const zoom of [1, 2]) {
      const r = await b.eval(`__sgRun(${bi}, ${view}, ${zoom})`);
      if (!r.steps) { console.log(`${key} #${bi} view ${view}: no step tiles`); break; }
      runs++;
      if (r.changed) fails++;
      console.log(`${key} (${r.at}) view ${view} zoom ${zoom * 100}%: ${r.steps} step tiles, ${r.changed} px changed`
                  + ` (${r.live} animating px left out)${r.sample ? " e.g. " + JSON.stringify(r.sample) : ""}`, r.changed ? "DIFF" : "same");
      if (SHOT) {
        await b.shot(`${SHOT}/steps_${key}_v${view}_z${zoom}_exe.png`);
        await b.eval("window.__sgKeep = window.stepGround, window.stepGround = () => new Set(), buildTerrain(), 0");
        await new Promise(r => setTimeout(r, 300));
        await b.shot(`${SHOT}/steps_${key}_v${view}_z${zoom}_ground.png`);
        await b.eval("window.stepGround = window.__sgKeep, buildTerrain(), 0");
      }
    }
  }
} finally {
  await b.eval("while (VIEW !== 0) rotateView(2); 0").catch(() => {});
  await b.close();
}
console.log(runs ? (fails ? `${fails} of ${runs} differ` : `all ${runs} the same`) : "no monument with step tiles");
process.exit(fails ? 1 : 0);
