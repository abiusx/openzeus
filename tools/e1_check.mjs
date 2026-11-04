// Track 1E rendering checks (docs/play/bugs.md, cart icon / bridge ghost / ramps), in headless muted Chrome at dpr 1.25
// with one device pixel per picture pixel (cam.zoom = 1 / dpr, as tools/oracle_view_compare.py):
//   node tools/e1_check.mjs http://127.0.0.1:PORT/play.html OUTDIR [--bridge X,Y] [--zoom 1|2]
// Run on your own server with a COPY of a save. Writes OUTDIR/cart.png + cart.json (the waiting cart's tile point on
// screen, where the exe draws its '?': re/oracle/runs/cartwait2), OUTDIR/bridge.png + bridge.json (the ghost's
// pixels inside the pieces' boxes: the exe ANDs them with 0x1FE3 in RGB555: red <= 7, blue <= 3 of 31) and the minimap's
// figure cells (black). tools/e1_check.py reads them.
import { launch } from "./play_cdp.mjs";
import { writeFileSync, mkdirSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [url, out] = a;
const zoomMul = +opt("--zoom", 1);
mkdirSync(out, { recursive: true });
const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
const sleep = ms => new Promise(r => setTimeout(r, ms));
try {
  await b.open(url + (url.includes("?") ? "&" : "?") + "tex=png");
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && objBatch && objBatch.n > 0", 180000);
  await b.eval("P.playing && togglePlay(), 0");
  // 1. waiting cart under See problems
  const cart = await b.eval(`(() => {
    const id = (P.f0.waiting || [])[0];
    const w = id != null && P.f0.walkers.find(w => w[0] === id);
    if (!w) return null;
    clampCam = () => {};
    cam.zoom = ${zoomMul} / devicePixelRatio;
    cam.x = tileX(w[1], w[2]) - 400 / cam.zoom / devicePixelRatio; cam.y = tileY(w[1], w[2]) - 300 / cam.zoom / devicePixelRatio;
    UIX.overlay = UIX.overlay || {}; UIX.overlay[UIX.page] = 18;
    const e = T.elev[w[2] * N + w[1]] || 0;
    return { id, x: w[1], y: w[2], dpx: Math.round((tileX(w[1], w[2]) - cam.x) * cam.zoom * devicePixelRatio),
             dpy: Math.round((tileY(w[1], w[2]) - e * 30 - cam.y) * cam.zoom * devicePixelRatio), scale: cam.zoom * devicePixelRatio };
  })()`);
  await sleep(1500);
  await b.shot(`${out}/cart.png`);
  // the minimap: walker cells are black (UIX.mm canvas)
  cart && (cart.minimap = await b.eval(`(() => { let n = 0, black = 0; const c = UIX.mm.ctx;
    for (const w of P.f0.walkers) { if (w[7] && w[7][0] === "hidden" || Overlays.walkerHidden(w[3], w[0]) && !w[3].startsWith("enemy_")) continue;
      const [px, py] = mmPx(w[1], w[2]), d = c.getImageData(px, py, 2, 1).data; n++; if (!(d[0] | d[1] | d[2] | d[4] | d[5] | d[6])) black++; }
    return [n, black]; })()`));
  writeFileSync(`${out}/cart.json`, JSON.stringify(cart));
  // 2. bridge ghost at a valid start tile
  const br = opt("--bridge");
  if (br) {
    const [bx, by] = br.split(",").map(Number);
    await b.eval(`(() => { UIX.overlay[UIX.page] = 0;
      cam.x = tileX(${bx}, ${by}) - 400 / cam.zoom / devicePixelRatio; cam.y = tileY(${bx}, ${by}) - 300 / cam.zoom / devicePixelRatio; return 1; })()`);
    await sleep(1200);
    await b.shot(`${out}/bridge0.png`);                    // the same view without the ghost: changed pixels = the ghost
    await b.eval(`(() => { selectTool({ key: "bridge" }); Build.hover = [${bx}, ${by}]; return 1; })()`);
    await sleep(1500);
    const g = await b.eval(`(() => { const fp = Build.fp; if (!fp || !fp.pieces) return null; const boxes = [];
      for (const [tx, ty, p] of fp.pieces) { const s = []; Bridges.draw(s, tx, ty, p); for (const e of s)
        boxes.push([Math.round((e[3] - cam.x) * cam.zoom * devicePixelRatio), Math.round((e[4] - cam.y) * cam.zoom * devicePixelRatio),
                    Math.round(e[2].w * cam.zoom * devicePixelRatio), Math.round(e[2].h * cam.zoom * devicePixelRatio)]); }
      return { pieces: fp.pieces, boxes }; })()`);
    await b.shot(`${out}/bridge.png`);
    writeFileSync(`${out}/bridge.json`, JSON.stringify(g));
  }
} finally { await b.close(); }
