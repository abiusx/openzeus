// Bridges in play mode: the exe's piece pictures (docs/logic/bridges.md "Drawing").
// The sim exports terrain.json `bridges` = [[tile index, piece]] (pieces from FUN_0041D720, stored at build).
// Bridge tiles stay water in the ground layer; each piece is an object drawn in the tile pass (city_draw ->
// FUN_0041D150): Zeus_General SPR_BRIDGE (packed 0x85A) + image index, at the tile's screen box
// (-31, -47) for the 119x100 pictures, (0, 0) for the 58x34 short ones. Pieces 1/6/7/12 (the end tiles) draw
// nothing: the ramp pictures of the next tile in cover them. In views 2 and 6 the piece is first turned
// (FUN_0041E410). Boats under a long bridge: drawn before the bridge piece of their tile (ours; see the doc).
"use strict";

const BRIDGE_IMAGE = { 2: 0, 3: 1, 4: 2, 5: 3, 8: 4, 10: 5, 9: 6, 11: 7, 13: 8, 14: 9 };       // FUN_0041D150 switch
const BRIDGE_TURN = { 1: 12, 2: 11, 3: 9, 4: 10, 5: 8, 6: 7, 7: 6, 8: 5, 9: 3, 10: 4, 11: 2, 12: 1, 13: 14, 14: 13 };  // FUN_0041E410

// FUN_0041D720 (not the race-track crossing): the piece of tile i of an n-tile span going in direction d (= sim
// game.bridge_piece); 13/14 short, 1/6/7/12 the end tiles (no picture)
function bridgePiece(i, n, d) {
  const ns = d === 0 || d === 4;
  if (n < 4) return ns ? 14 : 13;
  if (i === n - 1) return { 0: 12, 2: 6, 4: 7, 6: 1 }[d];
  if (i === 0) return { 0: 7, 2: 1, 4: 12, 6: 6 }[d];
  if (i === n - 2) return { 0: 11, 2: 5, 4: 8, 6: 2 }[d];
  if (i === 1) return { 0: 8, 2: 2, 4: 11, 6: 5 }[d];
  return ns ? 9 + (i & 1) : 4 - (i & 1);
}

const Bridges = {
  _T: null, map: new Map(),
  tiles() {                                       // tile index -> piece of the current terrain
    if (this._T !== T) { this._T = T; this.map = new Map((T && T.bridges) || []); }
    return this.map;
  },
  at(x, y) { return this.tiles().get(y * N + x); },
  // the picture and its top-left for piece p on tile (x, y); null for the end pieces
  draw(out, x, y, p, alpha) {
    const view = typeof VIEW !== "undefined" ? VIEW : 0;
    if (view === 2 || view === 6) p = BRIDGE_TURN[p] || p;
    const k = BRIDGE_IMAGE[p];
    if (k == null || !atlas.Zeus_General) return;
    const g = atlas.Zeus_General.groups.SPR_BRIDGE;
    const sp = g && sprite("Zeus_General", g[0] + k);
    if (!sp) return;
    const big = p < 13, el = (T.elev[y * N + x] || 0) * 30;
    const depth = window.Order ? Order.cell(x, y, Order.OBJECT) : x + y;   // city_draw step 3, at its cell (draw-order.md)
    const e = [depth, x, sp, tileX(x, y) + (big ? -31 : 0), tileY(x, y) - el + (big ? -47 : 0)];
    if (alpha != null) e.push(alpha);
    out.push(e);
  },
  // the Water Crossing tool's ghost (FUN_0041C8E0), composed apart from the built bridge: from the hovered tile A
  // (fp.pieces[0]) in the screen direction sd = (dir - view) & 7, pieces FUN_0041D720(i, n, sd) (no turn, no
  // mirror), stepping (+-29, +-15) per tile (half of the 58-px tile width, not the 60-px grid: the ghost drifts 1 px
  // per tile against the built pieces); long spans (n >= 4) draw i = 1..n-1 at (-32, -47), short ones i = 0..n-1
  // at (0, 0); for sd 0 / 6 the list is drawn again in reverse, so the nearer pieces end on top. Each entry
  // [order, x, sprite, left, top]; the caller ANDs the pixels with 0x1FE3 (gl.js alpha -1).
  ghost(out, fp) {
    const t = fp && fp.pieces, n = t ? t.length : 0;
    if (!n || fp.dir == null || !atlas.Zeus_General) return;
    const g = atlas.Zeus_General.groups.SPR_BRIDGE;
    const view = typeof VIEW !== "undefined" ? VIEW : 0, sd = (fp.dir - view + 8) & 7;
    const sx = sd <= 2 ? 29 : -29, sy = sd === 2 || sd === 4 ? 15 : -15, big = n >= 4;
    const [x0, y0] = t[0], X = tileX(x0, y0), Y = tileY(x0, y0) - (T.elev[y0 * N + x0] || 0) * 30;
    const seq = [];
    for (let i = big ? 1 : 0; i < n; i++) {
      const k = BRIDGE_IMAGE[bridgePiece(i, n, sd)], sp = k != null && g && sprite("Zeus_General", g[0] + k);
      if (sp) seq.push([t[i][0], sp, X + i * sx - (big ? 32 : 0), Y + i * sy - (big ? 47 : 0)]);
    }
    if (sd === 0 || sd === 6) seq.reverse();
    seq.forEach(([x, sp, l, tp], j) => out.push([Order.LAST + j, x, sp, l, tp]));
  },
  scene(out) {                                    // every bridge piece of the map
    if (!T || !T.bridges) return;
    for (const [i, p] of T.bridges) this.draw(out, i % N, (i / N) | 0, p);
  },
};
window.Bridges = Bridges;
