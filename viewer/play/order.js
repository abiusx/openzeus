// The exe's draw order (city_draw 0x00458170), as one sort key: docs/play/draw-order.md.
// Every drawer (buildings and their pieces/extras, walls, gardens, avenues, roadblocks, bridges, tall terrain,
// walkers, followers, standards, overlay columns) gets its key from here; play.js sorts the frame's list by it
// (stable: same key = push order, which is the exe's order inside one step of a cell).
//
// key = ((row * 512) + column + 256) * 8 + phase + sub, with row = a + b and column = a - b of the turned tile
// (a, b) = viewXY(x, y): the exe's cell walk, row by row, left to right. Inside a cell the exe draws, in order:
//   GROUND  raised / tall ground drawn again (pass 2 step 1)
//   OBJECT  bridge piece, the anchored object's top, its extras (steps 3-6)
//   DEFER4  walkers of the cell 4 rows up (two tiles behind) that the 0x0083AD6C grid says are drawn late
//   DEFER2  walkers of the cell 2 rows up: lifted figures (+0x1D: wall / tower sentries), and late ones
//   WALKER  this cell's own walkers, back to front by their offset in the tile (tile_walkers_sort 0x00449B30)
// Presentation only: reads VIEW, viewXY, worldXY, viewFoot, T, S, OCC (play.js), never the sim.
"use strict";

const Order = (() => {
  const GROUND = 0, OBJECT = 1, DEFER4 = 2, DEFER2 = 3, WALKER = 4;
  const LAST = 1e8;                                 // over every map key (third pass, ghosts)

  // debug (tools/draw_order_check.mjs): Order.meta = new Map() records what each key was made from
  const note = (k, m) => { if (Order.meta) Order.meta.set(k, m); return k; };
  const ab = (a, b, phase, sub = 0) => ((a + b) * 512 + (a - b) + 256) * 8 + phase + sub;
  const cell = (x, y, phase, sub = 0) => { const [a, b] = viewXY(x, y); return note(ab(a, b, phase, sub), { c: [x, y, phase] }); };
  // an object whose footprint is x..x+w-1, y..y+h-1: drawn at its left corner on screen (the exe's anchor)
  function obj(x, y, w = 1, h = w) {
    const f = viewFoot(x, y, w, h), [a, b] = viewXY(f.lx, f.ly);
    return note(ab(a, b, OBJECT), { o: [x, y, w, h] });
  }

  // --- the "walkers drawn later" grid (FUN_00448990), per tile in the current view: 0 own cell, 1 two rows
  // later, 2 four rows later. Computed lazily for the tiles that hold walkers, reset when the map, the state
  // or the view changes.
  let memo = null, memoT = null, memoS = null, memoV = -1;
  const inMap = (x, y) => x >= 0 && y >= 0 && x < N && y < N;
  const elevAB = (a, b) => { const [x, y] = worldXY(a, b); return inMap(x, y) ? (T.elev[y * N + x] || 0) : null; };
  const flagsAB = (a, b) => { const [x, y] = worldXY(a, b); return inMap(x, y) ? T.flags[y * N + x] : 0; };
  function corralOf(x, y) {                       // the ranch whose corral covers (x, y), or null
    const b = buildingAt(x, y), c = b && b.corral;
    return c && x >= c[0] && x < c[0] + 4 && y >= c[1] && y < c[1] + 4 ? b : null;
  }
  // "out" (outside the map), "nb" (0x10000000 without a building: neither), "blocked", "open"
  function classify(a, b) {
    const [x, y] = worldXY(a, b);
    if (!inMap(x, y)) return "out";
    const f = T.flags[y * N + x];
    let bd = buildingAt(x, y);
    if (bd && (bd.kind === "road" || bd.kind === "animal" || bd.key === "gardens" || corralOf(x, y))) bd = null;   // not exe buildings / corral 0x86 exempt
    if ((f & 0x10000000) && !bd) return "nb";
    if ((f & 0x4000) || (f & 0x4000040) === 0x4000040 || bd) return "blocked";
    return "open";
  }
  // a tile straight ahead (turned +1, +1) higher than walking down from (a, b) allows
  function higherAhead(a, b) {
    const e = elevAB(a, b), fl = flagsAB(a, b);
    for (let k = 0; k < 16; k++) {
      const a2 = a + k + 1, b2 = b + k + 1, [x2, y2] = worldXY(a2, b2);
      if (!inMap(x2, y2) || (T.flags[y2 * N + x2] & 0x80000)) break;          // map_in_play_area
      const e2 = T.elev[y2 * N + x2] || 0;
      if (e + k < e2) return true;
      if (e + k > 16) break;
      if (k === 0 && !(fl & 0x200) && (T.flags[y2 * N + x2] & 0x200) && e <= e2) return true;
    }
    return false;
  }
  function deferAB(a, b) {
    const c = classify(a, b);
    if (c === "out" || c === "blocked") return 0;
    if (c === "open" && higherAhead(a, b)) return 0;
    const [x, y] = worldXY(a, b), cr = corralOf(x, y);
    let base = 0;
    if (cr) { const [xa, ya] = worldXY(a + 1, b + 1); base = inMap(xa, ya) && corralOf(xa, ya) === cr ? 1 : 0; }
    for (const [da, db] of [[0, 1], [1, 0], [1, 1]]) if (classify(a + da, b + db) === "blocked") return base;
    for (const [da, db] of [[1, 2], [2, 2], [2, 1]]) {
      const k = classify(a + da, b + db);
      if (k === "blocked" || (k === "open" && higherAhead(a + da, b + db))) return 1;
    }
    return 2;
  }
  function defer(x, y) {
    if (memoT !== T || memoS !== S || memoV !== VIEW || !memo) {
      memo = new Int8Array(N * N).fill(-1); memoT = T; memoS = S; memoV = VIEW;
    }
    const i = y * N + x;
    if (memo[i] < 0) { const [a, b] = viewXY(x, y); memo[i] = deferAB(a, b); }
    return memo[i];
  }
  const isBridge = (x, y) => !!(window.Bridges && Bridges.at(x, y) != null);

  // a walker at fractional world tile (fx, fy). It belongs to the tile it is closest to (the exe moves it to the
  // next tile after 8 of 15 sub-steps). opts: lifted (+0x1D: sentry on a wall / tower), water (figure_on_water:
  // boats), rank (-100 / -50: drawn first in its tile; default its vertical offset in the tile).
  function walker(fx, fy, opts) {
    const o = opts || {}, k = walkerKey(fx, fy, o);
    if (o.big) {                                  // figure_type_on_tile 0x0045DAF0: a tile whose 0x0083AD6C byte is 0
      const x = Math.round(fx), y = Math.round(fy);
      if (inMap(x, y) && !isBridge(x, y) && defer(x, y) === 0) Order.big.add(y * N + x);
    }
    return note(k, { w: [fx, fy, o.lifted ? 1 : 0, o.water ? 1 : 0, o.rank != null ? o.rank : null, o.big ? 1 : 0] });
  }
  function walkerKey(fx, fy, o) {
    const x = Math.round(fx), y = Math.round(fy);
    const [fa, fb] = viewXY(fx, fy), [a, b] = viewXY(x, y);
    const r = o.rank != null ? o.rank : 15 * ((fa - a) + (fb - b));            // pixels below the tile centre
    const sub = Math.min(0.95, Math.max(0.02, 0.5 + r / 64));
    if (!inMap(x, y)) return ab(a, b, WALKER, sub);
    if (isBridge(x, y)) {                         // the bridge piece's tile: 0x0083AD6C forced to 1 while drawn
      if (o.water) return ab(a - 1, b - 1, WALKER, sub);   // ours: boats under the bridge (deviation, bridges.md)
      return ab(a + 1, b + 1, DEFER2, sub);
    }
    const g = defer(x, y);
    if (g === 1) return ab(a + 1, b + 1, DEFER2, sub);
    if (o.lifted) return ab(a + 1, b + 1, DEFER2, sub);
    if (g === 2 && !o.water) return ab(a + 2, b + 2, DEFER4, sub);
    return ab(a, b, WALKER, sub);
  }

  // pass 2 ground redraw (city_draw 0x004588A0..0x00458C2D) for a ground picture anchored at (x, y):
  // hasTop = the picture is taller than its base diamond (image +0x35), simple = flat-ground vegetation
  // (one tile, terrain & 0x881, not & 0x1000C208). true: draw it in the sorted list at its cell (GROUND);
  // false: it is ground (the terrain batch, under everything).
  function groundPass2(x, y, hasTop, simple) {
    const [a, b] = viewXY(x, y), e = elevAB(a, b) || 0, eb = elevAB(a - 1, b - 1);
    let iv = 0;
    if (eb != null) iv = e < eb ? 1 : e > eb ? -1 : ((flagsAB(a, b) & 0x200) && (flagsAB(a - 1, b - 1) & 0x800200)) ? 1 : 0;
    const aheadHigher = () => { const e2 = elevAB(a + 1, b + 1), e4 = elevAB(a + 2, b + 2); return (e2 != null && e2 > e) || (e4 != null && e4 > e + 1); };
    const redraw = () => {
      if (iv === -1) return !aheadHigher();
      for (let k = 1; k <= e; k++) { const ek = elevAB(a - k, b - k); if (ek == null) break; if (ek <= e - k) return true; }
      return false;
    };
    if (!hasTop || simple) return redraw();
    if (iv === 1) return redraw();
    return !aheadHigher();
  }

  // a picture the exe draws in pass 1 with the ground (city_draw 0x0045826C..: no top, or building types 2, 9,
  // roadblock 0x7B, corral 0x86 whose base is drawn there): under every sorted picture. Negative, one per tile.
  function pass1(x, y) { return note(-1 - (y * N + x), { p: [x, y] }); }

  // a ground picture anchored at (x, y) (play.js buildTerrain), in two parts like the exe: its BASE, drawn by
  // ground_tile_draw 0x00457900 in pass 1 (null: the terrain batch) or again at its cell (GROUND) when pass 2
  // step 1 redraws it (groundPass2); and, for a picture with a top (image +0x35), the TOP at step 4 of its anchor
  // cell (OBJECT; building_top_draw 0x005ADF00 at 0x004592A3, sloped_top_draw 0x0045A690 for blocks): the image's
  // upper h - (15n + 1) rows. simple = flat-ground vegetation (see groundPass2).
  function terrain(x, y, top, simple) {
    if (!groundPass2(x, y, top, simple)) { if (Order.meta) (Order.flat || (Order.flat = [])).push([x, y, top ? 1 : 0, simple ? 1 : 0, 0]); return null; }
    const [a, b] = viewXY(x, y);
    return note(ab(a, b, GROUND), { t: [x, y, top ? 1 : 0, simple ? 1 : 0, 0] });
  }
  function terrainTop(x, y, simple, n) {
    const [a, b] = viewXY(x, y);
    return note(ab(a, b, OBJECT), { t: [x, y, 1, simple ? 1 : 0, 1, n] });
  }
  // step 4 skips the top of a 1x1 piece whose terrain has none of 0x2DFED66F (plain grass, scrub 0x80, meadow
  // 0x800) when a figure of type 1, 4, 0xD, 0x1C, 0x2A, 0x43-0x45 (immigrant, cart, horseman, ox team, enemy
  // cavalry, god, monster, hero) stands on one of the two tiles behind it, cells (r - 1, c -/+ 1)
  // (city_draw 0x00459192..0x004591F8): the tufts never cover a cart's wheels. Order.big = those figures' tiles
  // this frame (walker() with opts.big).
  function topHidden(x, y, n) {
    if (n !== 1 || (T.flags[y * N + x] & 0x2dfed66f) || !Order.big.size) return false;
    const [a, b] = viewXY(x, y);
    for (const [da, db] of [[-1, 0], [0, -1]]) {
      const [x2, y2] = worldXY(a + da, b + db);
      if (inMap(x2, y2) && Order.big.has(y2 * N + x2)) return true;
    }
    return false;
  }

  return { GROUND, OBJECT, DEFER4, DEFER2, WALKER, LAST, ab, cell, obj, walker, defer, groundPass2, terrain, terrainTop, topHidden, pass1,
           big: new Set(), meta: null, flat: null };
})();
window.Order = Order;
