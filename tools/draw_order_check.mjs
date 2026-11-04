// Draw-order check for play mode (docs/play/draw-order.md "Check").
// Drives a headless Chrome (tools/play_cdp.mjs: own profile, muted) on a running server, captures the sorted draw
// list of a frame (play.js drawCapture + order.js Order.meta) in each of the 4 views, and compares the order of
// every pair of pictures whose screen boxes overlap with an independent reference of the exe's order:
//   - row / column from the exe's per-view grid formulas (rotation.md "Screen grid per view"), not viewXY;
//   - anchors from the per-view left-corner table, not viewFoot;
//   - the "walkers drawn later" grid as a literal port of FUN_00448990 with its per-view world-offset tables;
//   - phases and walker ranks as city_draw (0x00458170) walks a cell;
//   - no ground picture sorted on a building's tile, no grass/scrub/meadow top over a cart behind it (0x00459192).
// Besides the city's own walkers it injects test walkers (loaded carts, ox trains) stepping in quarter tiles along
// every road next to roadblocks, gatehouses, storehouses, trading posts, granaries, towers and the corral, both
// directions, and checks gatehouse arches (a walker in the passage is under SPR_GATE_OVERLAY, one on the road
// outside over it) and roadblocks (whatever the reference says, reported as over / under counts).
//
// Usage (start your own server on a COPY of a save, not a game in play):
//   python3 -m sim live /tmp/copy.pkl --port 8797 --speed 30 &
//   node tools/draw_order_check.mjs http://127.0.0.1:8797/play.html [--views 0,2,4,6] [--perf] [--shots DIR]
//        [--live SECONDS [--live-out DIR]]
// Exit code 1 when any violation is found. --perf prints drawFrame times (median / p90 over 8 s, view 0).
// --live S: then let the city run S seconds per view and check every sampled frame (whole map) with the city's own
// walkers at their real positions; --live-out DIR keeps the walkers that overlapped a roadblock (JSON per view).
// --shots DIR: a screenshot per view centred on each kind of target, with the test walkers drawn.
import { launch } from "./play_cdp.mjs";
import { mkdirSync, writeFileSync } from "node:fs";

const args = process.argv.slice(2), opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const URL_ = args[0];
const VIEWS = opt("--views", "0,2,4,6").split(",").map(Number);
const SHOTS = opt("--shots", null);
const LIVE = +opt("--live", 0), LIVE_OUT = opt("--live-out", null);   // seconds of the running city per view
if (!URL_) { console.error("usage: node tools/draw_order_check.mjs URL [--views 0,2,4,6] [--perf] [--shots DIR]"); process.exit(2); }

// ---------------------------------------------------------------- reference (exe) ----------------------------
// grid cell of world tile (x, y) in view v: [row, col2] (FUN_00449FF0; rotation.md)
function grid(v, x, y) {
  switch (v) {
    case 2: return [230 - x + y, 1 + x + y];
    case 4: return [455 - x - y, 230 - x + y];
    case 6: return [230 + x - y, 455 - x - y];
    default: return [1 + x + y, 230 + x - y];
  }
}
// left-corner tile of a w x h footprint at (x, y) (building_footprint_place 0x004A04B0)
function leftCorner(v, x, y, w, h) {
  if (v === 2) return [x, y];
  if (v === 4) return [x + w - 1, y];
  if (v === 6) return [x + w - 1, y + h - 1];
  return [x, y + h - 1];
}
// FUN_00448990 per-view offsets (world): front 3 (local_cc), second ring (local_d0), ahead step (0x005F84E0.. [8], [9])
const VT = {
  0: { cc: [[0, 1], [1, 0], [1, 1]], d0: [[1, 2], [2, 2], [2, 1]], step: [1, 1] },
  2: { cc: [[-1, 0], [-1, 1], [0, 1]], d0: [[-2, 1], [-2, 2], [-1, 2]], step: [-1, 1] },
  4: { cc: [[-1, 0], [-1, -1], [0, -1]], d0: [[-2, -1], [-2, -2], [-1, -2]], step: [-1, -1] },
  6: { cc: [[0, -1], [1, -1], [1, 0]], d0: [[1, -2], [2, -2], [2, -1]], step: [1, -1] },
};

function makeRef(D) {
  const { N, view: v, flags, elev, bridges } = D;
  const occ = new Int32Array(N * N), corral = new Int32Array(N * N);   // building index + 1; corral owner + 1
  D.buildings.forEach((b, k) => {
    if (b.kind === "road" || b.kind === "animal" || b.key === "gardens") return;
    for (let y = b.y; y < b.y + b.h; y++) for (let x = b.x; x < b.x + b.w; x++) if (x < N && y < N) occ[y * N + x] = k + 1;
    if (b.pier) for (let y = b.pier[1]; y < b.pier[1] + 2; y++) for (let x = b.pier[0]; x < b.pier[0] + 2; x++) occ[y * N + x] = k + 1;
    if (b.corral) for (let y = b.corral[1]; y < b.corral[1] + 4; y++) for (let x = b.corral[0]; x < b.corral[0] + 4; x++) corral[y * N + x] = k + 1;
  });
  const bridge = new Set(bridges.map(r => r[0]));
  const inMap = (x, y) => x >= 0 && y >= 0 && x < N && y < N;
  const el = (x, y) => elev[y * N + x] || 0;
  // pass 2 ground redraw of a flat picture (city_draw 0x004588A0..0x00458C2D), in world steps of this view
  function raised(x, y, simple) {
    const [sx, sy] = VT[v].step, e = el(x, y);
    const E = k => inMap(x + k * sx, y + k * sy) ? el(x + k * sx, y + k * sy) : null;
    const F = k => inMap(x + k * sx, y + k * sy) ? flags[(y + k * sy) * N + x + k * sx] : 0;
    const eb = E(-1);
    const iv = eb == null ? 0 : e < eb ? 1 : e > eb ? -1 : ((flags[y * N + x] & 0x200) && (F(-1) & 0x800200)) ? 1 : 0;
    if (iv === -1) { const e2 = E(1), e4 = E(2); return !((e2 != null && e2 > e) || (e4 != null && e4 > e + 1)); }
    for (let k = 1; k <= e; k++) { const ek = E(-k); if (ek == null) break; if (ek <= e - k) return true; }
    return false;
  }
  // pass 2 step 1 for any ground picture's base: one with a top that is not simple vegetation is drawn there
  // unless the tile behind is not higher and a tile ahead is (0x00458A19), else like a flat one
  function base(x, y, top, simple) {
    if (!top || simple) return raised(x, y, simple);
    const [sx, sy] = VT[v].step, e = el(x, y);
    const E = k => inMap(x + k * sx, y + k * sy) ? el(x + k * sx, y + k * sy) : null;
    const F = k => inMap(x + k * sx, y + k * sy) ? flags[(y + k * sy) * N + x + k * sx] : 0;
    const eb = E(-1);
    const iv = eb == null ? 0 : e < eb ? 1 : e > eb ? -1 : ((flags[y * N + x] & 0x200) && (F(-1) & 0x800200)) ? 1 : 0;
    if (iv === 1) return raised(x, y, simple);
    const e2 = E(1), e4 = E(2);
    return !((e2 != null && e2 > e) || (e4 != null && e4 > e + 1));
  }
  // open: the test at 0x00448B60 (roadblock 0x7B, corral 0x86 exempt; roads / gardens are terrain in the exe)
  function kind(x, y) {
    if (!inMap(x, y)) return "out";
    const i = y * N + x, f = flags[i], bd = occ[i] && !corral[i];
    if ((f & 0x10000000) && !bd) return "nb";
    if ((f & 0x4000) || (f & 0x4000040) === 0x4000040 || bd) return "blocked";
    return "open";
  }
  function higher(x, y) {
    const [sx, sy] = VT[v].step, e = el(x, y), fl = flags[y * N + x];
    let px = x, py = y;
    for (let k = 0; k < 16; k++) {
      px += sx; py += sy;
      if (!inMap(px, py) || (flags[py * N + px] & 0x80000)) break;
      if (e + k < el(px, py)) return true;
      if (e + k > 16) break;
      if (k === 0 && !(fl & 0x200) && (flags[py * N + px] & 0x200) && e <= el(px, py)) return true;
    }
    return false;
  }
  function late(x, y) {                               // value of 0x0083AD6C for the tile
    const k = kind(x, y);
    if (k === "out" || k === "blocked") return 0;
    if (k === "open" && higher(x, y)) return 0;
    let val = 0;
    const c = corral[y * N + x];
    if (c) { const [sx, sy] = VT[v].step; val = inMap(x + sx, y + sy) && corral[(y + sy) * N + x + sx] === c ? 1 : 0; }
    for (const [dx, dy] of VT[v].cc) if (kind(x + dx, y + dy) === "blocked") return val;
    for (const [dx, dy] of VT[v].d0) { const q = kind(x + dx, y + dy); if (q === "blocked" || (q === "open" && higher(x + dx, y + dy))) return 1; }
    return 2;
  }
  // step 4 skips the top of a 1x1 ground piece with none of terrain 0x2DFED66F when a figure of type 1, 4, 0xD, ...
  // (here: immigrant, cart, horseman) stands on one of the two tiles behind it, a tile whose 0x0083AD6C byte is 0
  // (city_draw 0x00459192, figure_type_on_tile 0x0045DAF0): tops drawn although they must not be
  const behind = VT[v].cc.filter(([dx, dy]) => dx !== VT[v].step[0] || dy !== VT[v].step[1]).map(([dx, dy]) => [-dx, -dy]);
  ref.topsOverCarts = list => {
    const big = new Set();
    for (const e of list) if (e.meta && e.meta.w && e.meta.w[5]) {
      const x = Math.round(e.meta.w[0]), y = Math.round(e.meta.w[1]);
      if (inMap(x, y) && !bridge.has(y * N + x) && late(x, y) === 0) big.add(y * N + x);
    }
    const bad = [];
    if (big.size) for (const e of list) if (e.meta && e.meta.t && e.meta.t[4] && e.meta.t[5] === 1) {
      const [x, y] = e.meta.t;
      if (flags[y * N + x] & 0x2dfed66f) continue;
      if (behind.some(([dx, dy]) => big.has((y + dy) * N + x + dx))) bad.push([x, y]);
    }
    return bad;
  };
  // reference position [row, col2, phase, rank] of a draw entry from its meta
  return ref;
  function ref(m) {
    if (m.p) return [-1e9, 0, 0, 0];                   // pass 1 (ground): roadblock, corral base
    if (m.o) { const [x, y, w, h] = m.o, [lx, ly] = leftCorner(v, x, y, w, h); return [...grid(v, lx, ly), 1, 0]; }
    if (m.c) { const [x, y, ph] = m.c; return [...grid(v, x, y), ph, 0]; }
    if (m.t) {                                        // ground picture: its top at step 4 (OBJECT), its base flat or at GROUND
      const [x, y, top, simple, part] = m.t;
      if (occ[y * N + x] && !corral[y * N + x]) return ["none"];   // a building's tile shows the building's picture
      if (part) return [...grid(v, x, y), 1, 0];
      return base(x, y, top, simple) ? [...grid(v, x, y), 0, 0] : ["batch"];
    }
    if (m.w) {
      const [fx, fy, lifted, water, rank] = m.w, x = Math.round(fx), y = Math.round(fy);
      const [r, c] = grid(v, x, y), rk = rank != null ? rank : 15 * (grid(v, fx, fy)[0] - r);
      const [sx, sy] = VT[v].step;
      const at = (n, ph) => { const [r2, c2] = grid(v, x + n * sx, y + n * sy); return [r2, c2, ph, rk]; };
      if (!inMap(x, y)) return [r, c, 4, rk];
      if (bridge.has(y * N + x)) return water ? at(-1, 4) : at(1, 3);   // ours: boats under the bridge (bridges.md)
      const g = late(x, y);
      if (g === 1 || lifted) return at(1, 3);
      if (g === 2 && !water) return at(2, 2);
      return [r, c, 4, rk];
    }
    return null;
  }
}
const cmp = (a, b) => { for (let i = 0; i < 4; i++) if (Math.abs(a[i] - b[i]) > 1e-6) return a[i] < b[i] ? -1 : 1; return 0; };

// overlapping pairs (grid buckets of 64 px) whose order differs from the reference
function check(C, ref, label, quiet) {
  const E = C.list;
  let flatBad = 0;                                  // ground pictures we draw flat that the exe sorts (tops: step 4)
  for (const t of C.flat) { const r = ref({ t }); if (r[0] !== "batch" && r[0] !== "none") { if (flatBad++ < 3) console.log("    drawn flat, exe sorts it:", JSON.stringify(t)); } }
  const R = E.map(e => e.meta ? ref(e.meta) : null);
  const overCarts = ref.topsOverCarts(E);           // tufts drawn over a cart behind them (bugs.md 185)
  for (const t of overCarts.slice(0, 3)) console.log("    ground top drawn over a cart behind it:", JSON.stringify(t));
  let onBuilding = 0;                               // ground pictures sorted on a building's tile (bugs.md 185)
  R.forEach((r, i) => { if (r && r[0] === "none") { if (onBuilding++ < 3) console.log("    ground picture on a building tile:", JSON.stringify(E[i].meta)); R[i] = null; } });
  const B = new Map(), bad = [];
  let pairs = 0;
  E.forEach((e, i) => {
    if (!R[i]) return;
    for (let gx = Math.floor(e.x / 64); gx <= Math.floor((e.x + e.w - 1) / 64); gx++)
      for (let gy = Math.floor(e.y / 64); gy <= Math.floor((e.y + e.h - 1) / 64); gy++) {
        const k = gx * 100003 + gy;
        let l = B.get(k); if (!l) B.set(k, l = []);
        l.push(i);
      }
  });
  const seen = new Set();
  for (const l of B.values()) for (let p = 0; p < l.length; p++) for (let q = p + 1; q < l.length; q++) {
    const i = Math.min(l[p], l[q]), j = Math.max(l[p], l[q]), a = E[i], b = E[j];
    if (!R[i] || !R[j]) continue;                     // every pair of placed pictures: walkers, ground, buildings, pieces
    const id = i * 1e6 + j;
    if (seen.has(id)) continue;
    seen.add(id);
    if (a.x >= b.x + b.w || b.x >= a.x + a.w || a.y >= b.y + b.h || b.y >= a.y + a.h) continue;
    pairs++;
    if (R[i][0] === "batch" || R[j][0] === "batch") { bad.push({ first: a.meta, second: b.meta, why: "ground picture sorted that the exe draws flat (pass 1)" }); continue; }
    if (cmp(R[i], R[j]) > 0) bad.push({ first: a.meta, second: b.meta, refFirst: R[i], refSecond: R[j] });   // drawn i before j, ref says after
  }
  if (!quiet || bad.length || flatBad || onBuilding || overCarts.length) console.log(`${label}: ${E.length} pictures (+${C.flat.length} flat ground), ${pairs} overlapping pairs checked, ${bad.length} out of order` + (flatBad ? `, ${flatBad} ground pictures wrongly flat` : "") + (onBuilding ? `, ${onBuilding} ground pictures on building tiles` : "") + (overCarts.length ? `, ${overCarts.length} tops over carts` : ""));
  for (const v of bad.slice(0, 5)) console.log("   ", JSON.stringify(v));
  return bad.length + flatBad + onBuilding + overCarts.length;
}

// ---------------------------------------------------------------- page side -----------------------------------
const PAGE = String.raw`
window.DOC = {
  data() {
    return { N, view: VIEW, flags: Array.from(T.flags), elev: Array.from(T.elev), road: Array.from(T.road, r => r ? 1 : 0), bridges: T.bridges || [], roadblocks: S.roadblocks || [],
      buildings: S.buildings.map(b => ({ key: b.key, kind: b.kind, x: b.x, y: b.y, w: b.w || b.size || 1, h: b.h || b.size || 1, pier: b.pier, corral: b.corral })) };
  },
  capture(all) {                                  // one frame's sorted list: [{x, y, w, h, meta, tag}]
    Order.meta = new Map();
    let L = null;
    window.drawCapture = l => { L = l.slice(); };
    const z = cam.zoom, cx = cam.x, cy = cam.y, cc = clampCam;
    try {
      buildTerrain();                             // ground pictures register their keys too
      if (all) { clampCam = () => {}; cam.zoom = 1e-3; cam.x = -1e5; cam.y = -1e5; }   // every tall ground picture is "on screen"
      drawFrame();
    } finally { window.drawCapture = null; clampCam = cc; cam.zoom = z; cam.x = cx; cam.y = cy; }
    const M = Order.meta, F = Order.flat || []; Order.meta = null; Order.flat = null;
    const gate = MAP.buildings.gatehouse, rb = MAP.buildings.roadblock;
    const tags = new Map();
    for (const i of [gate.overlay, gate.overlay + 1]) { const s = sprite(gate.file, i); tags.set(s, "gate_overlay"); tags.set(mirrored(s), "gate_overlay"); }
    { const s = sprite(rb.file, rb.base); tags.set(s, "roadblock"); tags.set(mirrored(s), "roadblock"); }
    const out = L.map(e => ({ x: e[3], y: e[4], w: e[2].w, h: e[2].h, meta: M.get(e[0]) || null, tag: tags.get(e[2]) || null }));
    return { list: out, flat: F };              // flat: ground pictures left in the terrain batch
  },
  // test walkers [id, role, good, amount, x0, y0, x1, y1, kk] instead of the city's (sceneWalkers reads P.f0)
  inject(list) {
    if (!DOC.orig) DOC.orig = Scene.sceneWalkers;
    Scene.sceneWalkers = out => {
      const a = P.f0, b = P.f1;
      P.f0 = { tick: a ? a.tick : 0, walkers: list.map(([id, role, good, amount, x0, y0, x1, y1, kk, look]) =>
        [id, x1, y1, role, good, amount, 0, look || null, [x0, y0, P.t - kk * 15, P.t - kk * 15 + 15]]), gone: [] };
      P.f1 = null;
      try { DOC.orig(out); } finally { P.f0 = a; P.f1 = b; }
    };
  },
  uninject() { if (DOC.orig) Scene.sceneWalkers = DOC.orig; },
  centre(x, y) {
    cam.x = tileX(x, y) + 29 - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
    cam.y = tileY(x, y) + 15 - innerHeight / 2 / cam.zoom;
  },
  where(x, y) { const e = (T.elev[y * N + x] || 0) * 30; return [(tileX(x, y) + 29 - cam.x) * cam.zoom * devicePixelRatio, (tileY(x, y) + 15 - e - cam.y) * cam.zoom * devicePixelRatio]; },
  setView(v) { let n = 0; while (VIEW !== v && n++ < 4) rotateView(2); return VIEW; },
};`;

// roads next to the targets and the steps along them
function scenarios(D) {
  const { N, buildings, roadblocks } = D;
  const road = new Set();
  D.road.forEach((r, i) => { if (r) road.add(i); });
  for (const [x, y] of roadblocks) road.add(y * N + x);
  const isRoad = (x, y) => x >= 0 && y >= 0 && x < N && y < N && road.has(y * N + x);
  const want = { roadblock: [], gatehouse: [], storehouse: [], trading_post: [], granary: [], tower: [], horse_ranch: [], dock: [] };
  for (const [x, y] of roadblocks) want.roadblock.push({ x, y, w: 1, h: 1 });
  for (const b of buildings) if (want[b.key]) want[b.key].push(b);
  const out = [];
  for (const [kind, list] of Object.entries(want)) for (const b of list.slice(0, 6)) {
    const box = b.corral ? { x: Math.min(b.x, b.corral[0]), y: Math.min(b.y, b.corral[1]), w: 0, h: 0 } : b;
    const x0 = box.x - 1, y0 = box.y - 1, x1 = (b.corral ? Math.max(b.x + b.w, b.corral[0] + 4) : b.x + b.w), y1 = (b.corral ? Math.max(b.y + b.h, b.corral[1] + 4) : b.y + b.h);
    const tiles = [];
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) if (isRoad(x, y)) tiles.push([x, y]);
    const steps = [];
    for (const [x, y] of tiles) for (const [dx, dy] of [[1, 0], [0, 1], [-1, 0], [0, -1]]) if (isRoad(x + dx, y + dy)) steps.push([x, y, x + dx, y + dy]);
    if (steps.length) out.push({ kind, at: [b.x, b.y], steps });
  }
  // wall sentries (lifted, +0x1D) walking on the wall tops next to towers and gatehouses (bugs.md 178)
  const wallTop = (x, y) => x >= 0 && y >= 0 && x < N && y < N && ((D.flags[y * N + x] & 0x4000) ||
    buildings.some(q => (q.key === "tower" || q.key === "gatehouse") && x >= q.x && y >= q.y && x < q.x + q.w && y < q.y + q.h));
  for (const b of buildings.filter(q => q.key === "tower" || q.key === "gatehouse").slice(0, 6)) {
    const steps = [];
    for (let y = b.y - 3; y <= b.y + b.h + 2; y++) for (let x = b.x - 3; x <= b.x + b.w + 2; x++) if (wallTop(x, y))
      for (const [dx, dy] of [[1, 0], [0, 1], [-1, 0], [0, -1]]) if (wallTop(x + dx, y + dy)) steps.push([x, y, x + dx, y + dy]);
    if (steps.length) out.push({ kind: "sentries_" + b.key, at: [b.x, b.y], steps, sentry: true });
  }
  return out;
}

// ---------------------------------------------------------------- main ----------------------------------------
const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
let total = 0, nextId = 900000;                  // fresh ids: no ox trail left from another test walker
try {
  await b.open(URL_);
  await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && window.Order && objBatch && objBatch.n > 0", 180000);
  await b.eval(PAGE);
  await b.eval("P.playing && togglePlay(), 0");                // pause the city: the frames stay put
  await new Promise(r => setTimeout(r, 1500));
  if (args.includes("--perf")) {
    await b.eval("DOC.setView(0)");
    const r = await b.eval(`new Promise(res => { const f = drawFrame, ts = []; drawFrame = function () { const t = performance.now(); f(); ts.push(performance.now() - t); };
      setTimeout(() => { drawFrame = f; ts.sort((a, c) => a - c); res({ frames: ts.length, median_ms: ts[ts.length >> 1], p90_ms: ts[Math.floor(ts.length * 0.9)] }); }, 8000); })`);
    console.log("perf (drawFrame, view 0, 8 s):", JSON.stringify(r));
  }
  for (const v of VIEWS) {
    await b.eval(`DOC.setView(${v})`);
    await new Promise(r => setTimeout(r, 1500));               // turned terrain rebuilt
    const D = await b.eval("DOC.data()"), ref = makeRef(D);
    total += check(await b.eval("DOC.capture()"), ref, `view ${v} city`);
    total += check(await b.eval("DOC.capture(true)"), ref, `view ${v} whole map (every ground picture)`);
    let gateBad = 0, gateN = 0, rbOver = 0, rbUnder = 0; const rbWhy = [];
    for (const sc of scenarios(D)) {
      for (const kk of [0, 0.25, 0.5, 0.75]) {
        const W = sc.steps.map((s, i) => sc.sentry ? [(nextId += 1), "wall_sentry", null, 0, s[0], s[1], s[2], s[3], kk, ["walk", 0, 0, 0, 0, 0, 0, 0, "", false, [18]]]
          : [(nextId += 1), "cart", i % 3 === 2 ? "marble" : "wheat", 300, s[0], s[1], s[2], s[3], kk]);
        await b.eval(`DOC.inject(${JSON.stringify(W)})`);
        const C = await b.eval("DOC.capture()"), E = C.list;
        total += check(C, ref, `view ${v} ${sc.kind} (${sc.at}) kk ${kk}`) ? 1 : 0;
        // gatehouse arch: walkers drawn before an overlapping overlay must stand on a gatehouse tile
        const G = new Set(D.buildings.filter(q => q.key === "gatehouse").flatMap(q => { const t = []; for (let y = q.y; y < q.y + q.h; y++) for (let x = q.x; x < q.x + q.w; x++) t.push(y * D.N + x); return t; }));
        E.forEach((o, j) => {
          if (o.tag !== "gate_overlay" && o.tag !== "roadblock") return;
          E.forEach((w, i) => {
            if (!w.meta || !w.meta.w || w.x >= o.x + o.w || o.x >= w.x + w.w || w.y >= o.y + o.h || o.y >= w.y + w.h) return;
            const tx = Math.round(w.meta.w[0]), ty = Math.round(w.meta.w[1]);
            if (o.tag === "roadblock") { if (i > j) rbOver++; else { rbUnder++; if (rbWhy.length < 4) rbWhy.push([tx, ty, ref(w.meta)]); } return; }
            if (!G.has(ty * D.N + tx) || w.meta.w[2]) return;  // off the gatehouse, or lifted (+0x1D: drawn 2 rows later, over it): the pair check
            gateN++;
            if (i > j) { gateBad++; console.log("    gate: walker over the arch at", tx, ty, JSON.stringify(w.meta.w), "arch", o.x, o.y); }   // in the passage: must be under it
          });
        });
        await b.eval("DOC.uninject()");
      }
      if (SHOTS) {
        mkdirSync(SHOTS, { recursive: true });
        const W = sc.steps.map((s, i) => sc.sentry ? [(nextId += 1), "wall_sentry", null, 0, s[0], s[1], s[2], s[3], 0.5, ["walk", 0, 0, 0, 0, 0, 0, 0, "", false, [18]]]
          : [(nextId += 1), "cart", i % 3 === 2 ? "marble" : "wheat", 300, s[0], s[1], s[2], s[3], 0.5]);
        await b.eval(`DOC.inject(${JSON.stringify(W)}); DOC.centre(${sc.at[0]}, ${sc.at[1]})`);
        await new Promise(r => setTimeout(r, 400));
        const name = `${SHOTS}/v${v}_${sc.kind}_${sc.at.join("_")}`;
        await b.shot(name + ".png");
        writeFileSync(name + ".json", JSON.stringify(await b.eval(`DOC.where(${sc.at[0]}, ${sc.at[1]})`)));   // target in device px
        await b.eval("DOC.uninject()");
      }
    }
    if (LIVE) {                                    // the city's own walkers, running (bugs.md 203)
      await b.eval("P.playing || togglePlay(), 0");
      let frames = 0, bad = 0, over = 0, under = 0; const seen = new Set(), rec = [];
      for (const t0 = Date.now(); Date.now() - t0 < LIVE * 1000;) {
        const C = await b.eval("DOC.capture(true)"), E = C.list;
        frames++;
        bad += check(C, ref, `view ${v} live frame ${frames}`, true) ? 1 : 0;
        E.forEach((o, j) => {
          if (o.tag !== "roadblock") return;
          E.forEach((w, i) => {
            if (!w.meta || !w.meta.w || w.x >= o.x + o.w || o.x >= w.x + w.w || w.y >= o.y + o.h || o.y >= w.y + w.h) return;
            if (i > j) over++; else under++;
            seen.add(Math.round(o.x) + "," + Math.round(o.y));
            if (rec.length < 2000) rec.push({ view: v, t: frames, walker: w.meta.w, over: i > j, rb: [o.x, o.y] });
          });
        });
        await new Promise(r => setTimeout(r, 150));
      }
      await b.eval("P.playing && togglePlay(), 0");
      if (LIVE_OUT) { mkdirSync(LIVE_OUT, { recursive: true }); writeFileSync(`${LIVE_OUT}/v${v}.json`, JSON.stringify(rec)); }
      console.log(`view ${v} live ${LIVE} s: ${frames} frames, ${bad} with problems; city walkers overlapping a roadblock: over it ${over}, under it ${under} (${seen.size} roadblocks)`);
      total += bad + under;
    }
    console.log(`view ${v}: gatehouse arch ${gateN - gateBad}/${gateN} as exe (walkers in the passage under it); test carts overlapping a roadblock: drawn over it ${rbOver}, under it ${rbUnder}` + (rbWhy.length ? ` (e.g. walker tile, ref [row, col2, phase, rank]: ${JSON.stringify(rbWhy)})` : ""));
    total += gateBad + rbUnder;                     // a roadblock is ground (pass 1): nothing is ever under it
  }
  const errs = b.logs.filter(l => /EXC|Error/.test(l));
  if (errs.length) console.log("page errors:", errs.slice(0, 5));
} finally { await b.close(); }
console.log(total ? `FAIL: ${total} problems` : "OK: draw order as the exe's in every checked pair");
process.exit(total ? 1 : 0);
