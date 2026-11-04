// Play-mode check of the marble quarry / black marble shop yard figure (city_draw case 0x31 / 0xD5 -> FUN_0045C170;
// docs/play/buildings.md 7c, bugs.md 454). Headless Chrome (tools/play_cdp.mjs: own profile, muted) on your own
// server with a COPY of a save that has a staffed quarry:
//   node tools/quarry_yard_check.mjs http://127.0.0.1:PORT/play.html [DIR]
// For the first quarry in the snapshot it draws the building (scene.js drawBuilding) with its stock set to 0, 100, ..
// 800, unstaffed and burning, and checks the yard sprite against the exe rule: staffed, not burning; stock 0 -> idle
// figure (SprAmbient 2437 / 2277 by grid_random, dir 3) at (0x3B, 0x1B); stock s -> stonecutter (2017, n 7: 1937) at
// the table position for s // 100 - 1. Also every real quarry as it is now. With DIR: shots centred on that quarry in
// views 0, 2, 4, 6 at zoom 100 % and 200 % (original sprites, ?tex=png). Exit 1 on a mismatch.
import { launch } from "./play_cdp.mjs";
import { mkdirSync } from "node:fs";

const [URL_, DIR] = process.argv.slice(2);
if (!URL_) { console.error("usage: node tools/quarry_yard_check.mjs URL [DIR]"); process.exit(2); }
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PAGE = String.raw`
window.QY = {
  TAB: [[0x3B, 0x29, 7, 2017], [0x3F, 0x32, 0, 2017], [0x37, 0x2D, 6, 2017], [0x3B, 0x33, 7, 2017],
        [0x3B, 0x25, 7, 2017], [0x3E, 0x29, 0, 2017], [0x3D, 0x25, 6, 2017], [0x3F, 0x33, 7, 1937]],
  // the SprAmbient picture among the drawn ones, as [first of its group, dir, x - tl.x, y - tl.y] (view 0, no mirror)
  yard(b) {
    const out = [], m = MAP.buildings[b.key];
    drawBuilding(out, b, m);
    const base = out[0], hits = [];
    for (const e of out.slice(1)) for (const [first, n] of [[2017, 80], [1937, 80], [2437, 96], [2277, 160]])
      for (let i = 0; i < n; i++) if (e[2] === sprite("SprAmbient", first + i)) hits.push([first, i % 8, e[3] - base[3], e[4] - base[4], e[2].ax, e[2].ay, base[2].h]);
    return hits;
  },
  expect(b) {
    if (b.burning || !(b.employees > 0)) return null;
    const s = (b.goods || {})[b.key === "marble_quarry" ? "marble" : "black_marble"] || 0;
    if (s === 0) return [tileRand(b.x, b.y) & 1 ? 2277 : 2437, 3, 0x3B, 0x1B];
    const [dx, dy, d, f] = QY.TAB[Math.min(Math.floor(s / 100), 8) - 1];
    return [f, d, dx, dy];
  },
  check(b) {
    const h = QY.yard(b), e = QY.expect(b);
    if (!e) return h.length ? "drawn but should not be: " + JSON.stringify(h) : "ok (none)";
    if (h.length !== 1) return "expected one yard figure, got " + JSON.stringify(h);
    const [f, d, x, y, ax, ay, bh] = h[0];
    const ex = e[2] - ax, ey = bh - 45 + e[3] - ay;      // draw point (base_left, base_bottom - 15*(n+1)), n = 2
    return f === e[0] && d === e[1] && x === ex && y === ey ? "ok " + JSON.stringify([f, d, x, y])
      : "MISMATCH got " + JSON.stringify([f, d, x, y]) + " want " + JSON.stringify([e[0], e[1], ex, ey]);
  },
  run() {
    const Q = S.buildings.filter(b => b.key === "marble_quarry" || b.key === "black_marble_shop");
    if (!Q.length) return { error: "no quarry in the snapshot" };
    const res = [], v = VIEW;
    while (VIEW !== 0) rotateView(2);
    const g = Q[0].key === "marble_quarry" ? "marble" : "black_marble";
    for (const s of [0, 100, 200, 300, 400, 500, 600, 700, 800])
      res.push(["stock " + s, QY.check({ ...Q[0], employees: 15, burning: 0, goods: s ? { [g]: s } : {} })]);
    res.push(["unstaffed 800", QY.check({ ...Q[0], employees: 0, burning: 0, goods: { [g]: 800 } })]);
    res.push(["burning 800", QY.check({ ...Q[0], employees: 15, burning: 1, goods: { [g]: 800 } })]);
    for (const b of Q) res.push([b.key + " " + b.id + " (" + b.x + "," + b.y + ") emp " + b.employees + " " + JSON.stringify(b.goods), QY.check(b)]);
    while (VIEW !== v) rotateView(2);
    return { res, first: [Q[0].x, Q[0].y] };
  },
  setView(v) { let n = 0; while (VIEW !== v && n++ < 4) rotateView(2); return VIEW; },
  centre(x, y, z) {
    clampCam = () => {};
    cam.zoom = z / devicePixelRatio;
    const e = (T.elev[y * N + x] || 0) * 30;
    cam.x = Math.round(tileX(x, y) + 29 - (UIX.panelX * UIX.scale) / 2 / cam.zoom);
    cam.y = Math.round(tileY(x, y) + 15 - e - innerHeight / 2 / cam.zoom);
    return [cam.x, cam.y];
  },
};
true`;

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
let bad = 0;
try {
  await b.open(URL_ + (URL_.includes("?") ? "&" : "?") + "tex=png");
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && window.Order && objBatch && objBatch.n > 0", 180000);
  await b.eval(PAGE);
  await b.eval("P.playing && togglePlay(), 0");
  await sleep(1000);
  const r = await b.eval("QY.run()");
  if (r.error) { console.log(r.error); bad = 1; }
  else for (const [k, v] of r.res) { console.log(k.padEnd(60), v); if (!v.startsWith("ok")) bad = 1; }
  if (DIR && r.first) {
    mkdirSync(DIR, { recursive: true });
    for (const v of [0, 2, 4, 6]) {
      await b.eval(`QY.setView(${v})`);
      await sleep(1200);
      for (const z of [1, 2]) {
        await b.eval(`QY.centre(${r.first[0] + 1}, ${r.first[1] + 1}, ${z})`);
        await sleep(300);
        await b.shot(`${DIR}/quarry_view${v}_z${z * 100}.png`);
      }
    }
    await b.eval("QY.setView(0)");
    console.log("shots ->", DIR);
  }
} finally { await b.close(); }
process.exit(bad);
