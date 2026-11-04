// Play-mode monuments: sanctuaries, Poseidon pyramids and the palace, drawn piece by piece.
// Rules: docs/play/monuments.md; data: data/play/monuments.json (tools/play_monuments.py).
// Input b = a monument of state.json: {key, x, y, w, h, employees, built, pieces: [[dx, dy, class, elev, stage, stages], ...]}.
// Output: draws [depth, tiebreak, sprite, left, top] into `out` (same convention as scene.js place()).
// ctx: {sprite(file, index), tileX(x, y), tileY(x, y), elevPx(x, y)} and optionally rand(x, y) (per-tile
// random bits), data (monuments.json; default: MAP.monuments) and now (ms clock; default performance.now()).
"use strict";
(function () {
  function hash(x, y) {
    let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) | 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return (h ^ (h >>> 16)) >>> 0;
  }
  const dataOf = ctx => ctx.data || (typeof MAP !== "undefined" && MAP.monuments) || null;

  // placement orientation o = b.orient (0..3; exe b+0x9C, composite_offset_rotate in FUN_0053D9A0 / FUN_0053C390):
  // the layout turned by 90 degrees per step; a piece of n tiles at (dx, dy) in the W x H layout box goes to
  // o1 (dy, W-dx-n), o2 (W-dx-n, H-dy-n), o3 (H-dy-n, dx); the box is H x W for 1 and 3 (bugs.md 133)
  function turned(D, L, b) {
    const o = (b.orient || 0) & 3;
    if (!o) return [L, b, 0];
    const W = L.w, H = L.h;
    const pieces = b.pieces.map(p => {
      const [dx, dy, c] = p, n = (D.classes[c] || { size: 1 }).size || 1;
      const xy = o === 1 ? [dy, W - dx - n] : o === 2 ? [W - dx - n, H - dy - n] : [H - dy - n, dx];
      return [xy[0], xy[1], ...p.slice(2)];
    });
    return [Object.assign({}, L, { w: o % 2 ? H : W, h: o % 2 ? W : H }), Object.assign({}, b, { pieces }), o];
  }
  // the class images for orientation o (re_monument_images.py emulates vt+0x4C with b+0x9C = o)
  function phasesOf(D, cls, o, view) {
    const pos = D.mode === "poseidon";
    // turned views: the exe's image also reads the view 0x00DA2F88 (emulated per view, docs/play/rotation.md)
    const vp = view && ((pos && cls.view_poseidon_phases) || cls.view_phases);
    if (vp && vp[view] && vp[view][o]) return vp[view][o];
    if (o && cls.orient_phases && cls.orient_phases[o])
      return (pos && cls.orient_poseidon_phases && cls.orient_poseidon_phases[o]) || cls.orient_phases[o];
    return (pos && cls.poseidon_phases) || cls.phases;
  }

  // built height of every tile of the monument, in the original's height steps (30 px each)
  function heights(D, L, b) {
    const w = L.w, H = new Int8Array(w * L.h), member = new Uint8Array(w * L.h);
    const ph = [];
    b.pieces.forEach((p, i) => {
      const [dx, dy, c, , s] = p, cls = D.classes[c] || { size: 1 }, e = L.elev[i];
      let h = e;
      if (L.kind === "pyramid" && c < 1000) {
        const E = (e >> 1) * 4;                     // base stages: 4 per level of 2 steps (monuments.md)
        if (s < E) h = 2 * Math.floor(s / 4);
      }
      ph.push(h);
      const n = cls.size || 1;
      for (let j = 0; j < n; j++) for (let k = 0; k < n; k++) {
        const t = (dy + j) * w + dx + k;
        if (t < 0 || t >= H.length) continue;
        H[t] = h;
        if (c < 1000) member[t] = 1;
      }
    });
    return { H, member, ph };
  }

  // exe 0x00545940: step image of tile (tx, ty) (box coords) from its 8 neighbours' heights
  // turned views: neighbour i is world direction (i + view) & 7 (table 0x005D9888[(view + i) & 7]); a pyramid's
  // full step shape is mirrored back in views 2 and 6 (0, 7, 6, .. 1: its piece picture is mirrored there)
  function stepSprite(D, L, G, ctx, tx, ty, variant, base) {
    const S = D.steps, w = L.w, h0 = G.H[ty * w + tx], view = ctx.view || 0;
    let mask = 0, half = 0, full = 0;
    for (let i = 0; i < 8; i++) {
      const nb = S.neighbours[(i + view) & 7], nx = tx + nb[0], ny = ty + nb[1];
      const inside = nx >= 0 && ny >= 0 && nx < w && ny < L.h;
      const d = (inside ? G.H[ny * w + nx] : 0) - h0 + 2;
      if (d < 0 || d > 4) return null;
      if (d === 3) { mask |= 1 << i; half++; }
      else if (d === 4) { mask |= 1 << i; full++; }
    }
    if (!mask) return null;
    let shape = S.shapes[mask];
    if (shape == null) return null;
    if (half) {
      if (full) return null;
      const im = S.half.improved;
      if (im.shapes.includes(shape)) return ctx.sprite(im.file, im.first + shape - im.shapes[0]);
      return ctx.sprite(S.half.file, S.half.first + shape);
    }
    if (shape > 7) return null;
    if (L.kind === "pyramid" && (view === 2 || view === 6)) shape = (8 - shape) & 7;
    // base variants: a ground-level piece at the monument's edge (one of its 8 neighbours is not part of it)
    let edge = false;
    if (base) for (const [ox, oy] of S.neighbours) {
      const nx = tx + ox, ny = ty + oy;
      if (nx < 0 || ny < 0 || nx >= w || ny >= L.h || !G.member[ny * w + nx]) { edge = true; break; }
    }
    const g = edge ? S.full.base : S.full.plain;    // [plain, decorated faces, black, black decorated]
    const v = variant;
    let first, off;
    if (shape === 3) {
      if (v === 0) [first, off] = [g[0], 3]; else if (v <= 4) [first, off] = [g[1], v - 1];
      else if (v === 5) [first, off] = [g[2], 3]; else if (v <= 8) [first, off] = [g[3], v - 6]; else [first, off] = [g[3], 3];
    } else if (shape === 5) {
      if (v === 0) [first, off] = [g[0], 5]; else if (v <= 4) [first, off] = [g[1], 8 - v];
      else if (v === 5) [first, off] = [g[2], 5]; else [first, off] = [g[3], 13 - v];
    } else [first, off] = [v < 5 ? g[0] : g[2], shape];
    return ctx.sprite(S.full.file, first + off);
  }

  // priestess piece classes (0x0044EE80 class methods vt+0xB0 front, +0xB4 back, +0xCC grand temple)
  const FRONT = new Set([0, 158, 110]), PRIEST = new Set([0, 1, 110, 158, 159]), GRAND = new Set([158, 159]);

  function frame(a, now, k) {
    return a.first + a.stride * (Math.floor(now / a.ms + (k || 0)) % a.frames);
  }

  function draw(out, b, ctx) {
    const D = dataOf(ctx);
    if (!D || !b.pieces) return;
    let L = D.layouts[b.key], o;
    if (!L) return;
    [L, b, o] = turned(D, L, b);
    const G = heights(D, L, b);
    const rand = ctx.rand || hash, now = ctx.now != null ? ctx.now : performance.now();
    const complete = (b.built || 0) >= 100;
    // one image of an n-tile object whose min tile is (x, y), raised by h steps
    // ground: a terrain-like step tile (extras, flag 0x10000000), never mirrored (oracle: sanctuary terraces in views
    // 2/6 match only unmirrored); pieces are buildings, mirrored in views 2 and 6
    const put = (sp, x, y, n, h, flat, ground) => {
      if (!sp) return null;
      // view (docs/play/rotation.md): ctx.viewFoot gives the top-corner tile and depth in the current view
      const f = ctx.viewFoot ? ctx.viewFoot(x, y, n, n) : { ax: x, ay: y, depth: x + y + 2 * (n - 1) };
      if (ctx.mirror && !ground) sp = ctx.mirror(sp);
      const left = ctx.tileX(f.ax, f.ay) - 30 * (n - 1);
      const top = ctx.tileY(f.ax, f.ay) + 30 * n - sp.h - ctx.elevPx(f.ax, f.ay) - D.pixels_per_height * h;
      out.push([ctx.order ? ctx.order(x, y, n, flat) : f.depth - (flat ? 0.5 : 0), x, sp, left, top]);
      return [left, top];
    };
    const perTile = (x, y, n, h, pick) => {
      for (let j = 0; j < n; j++) for (let k = 0; k < n; k++) {
        const sp = pick(x + k, y + j);
        if (sp) put(sp, x + k, y + j, 1, h, sp.h <= 31);
      }
    };
    const rough = (x, y) => ctx.sprite(D.rough.file, D.rough.first + rand(x, y) % D.rough.count);
    b.pieces.forEach((p, i) => {
      const [dx, dy, c, , s] = p, cls = D.classes[c];
      if (!cls) return;
      const x = b.x + dx, y = b.y + dy, n = cls.size || 1, h = G.ph[i], e = L.elev[i];
      if (cls.ground) {                              // extras (terrain tiles): steps toward higher neighbours
        const sp = stepSprite(D, L, G, ctx, dx, dy, 0, false);
        if (sp) put(sp, x, y, 1, h, false, true);
        return;
      }
      const phases = phasesOf(D, cls, o, ctx.view || 0);   // per view (oracle: palace halves as the exe)
      const E = L.kind === "pyramid" ? (e >> 1) * 4 : 0;
      if (s < E || (E && s === E)) {                  // pyramid base: rough, rising blocks, then the level's flat top
        if (s === 0) return perTile(x, y, n, h, rough);
        const bf = D.blocks.first, idx = s % 4 === 0 ? bf + 4 : bf + (s - 1) % 4;
        return perTile(x, y, n, h, () => ctx.sprite(D.blocks.file, idx));
      }
      const ph = phases[Math.min(s - E, phases.length - 1)];
      if (ph === "rough") return perTile(x, y, n, h, rough);
      if (!ph) return;
      if (ph.steps != null) {
        let sp = stepSprite(D, L, G, ctx, dx, dy, ph.steps, e === 0);
        if (!sp) sp = ctx.sprite(D.blocks.file, D.blocks.first + 4);   // ours: no higher neighbour yet
        if (sp) put(sp, x, y, 1, h, false);
        return;
      }
      const sp = ctx.sprite(ph.file, ph.index);
      if (!sp) return;
      const nn = sp.iso || n;
      const tl = put(sp, x, y, nn, h, sp.h <= 31 && nn === 1);
      if (!tl) return;
      const done = s >= p[5];
      // the original's draw point of a piece: its left-corner tile in the current view ((0, n-1) v0, (0, 0) v2,
      // (n-1, 0) v4, (n-1, n-1) v6), raised (exe city_draw 0x00458170 passes it to the picture and the figures)
      const A = D.anims, lf = ctx.viewFoot ? ctx.viewFoot(x, y, nn, nn) : { lx: x, ly: y + nn - 1 };
      const ox = ctx.tileX(lf.lx, lf.ly), oy = ctx.tileY(lf.lx, lf.ly) - ctx.elevPx(lf.lx, lf.ly) - D.pixels_per_height * h;
      const depth = ctx.order ? ctx.order(x, y, nn, false) : x + y + 2 * (nn - 1);   // the piece's own key: extras after it
      const view = ctx.view || 0;
      // a figure frame at anchor (px, py); turned over = flipped left-right, left = px - (w - ax) (0x005AE9F0; the
      // SprAmbient frames have no mirror copies); y is never mirrored (docs/play/monuments.md 6a)
      const fig = (f, px, py, flip) => {
        if (!f) return;
        if (flip && ctx.flip) { const m = ctx.flip(f); out.push([depth, x, m, px - m.ax - 1, py - f.ay]); }
        else out.push([depth, x, f, px - f.ax, py - f.ay]);
      };
      // priestesses (0x0044EE80): front piece (0, 158) / back piece (1, 159) / one-piece temple (110) by view and
      // d = 2 * orientation (+2 for the grand temple); turned over in views 2/6 when d == 0, in 0/4 when d == 2
      if (done && PRIEST.has(c) && (b.employees || 0) > 0) {
        const d = GRAND.has(c) ? (2 * o + 2) & 7 : 2 * o;
        const show = c === 110 || (FRONT.has(c) ? (d === 0 ? view === 0 || view === 2 : view === 0 || view === 6)
                                                : (d === 0 ? view === 4 || view === 6 : view === 2 || view === 4));
        if (show) {
          const flip = (view === 2 || view === 6) ? d === 0 : d === 2;
          const px = flip ? ox + 2 * ((sp.w + 1) >> 1) - A.priestesses.dx : ox + A.priestesses.dx;
          fig(ctx.sprite(A.priestesses.file, frame(A.priestesses, now)), px, oy + A.priestesses.dy, flip);
        }
      }
      // fire pots (0x0055B6E0): no view test; 1x1 pieces, so their own tile is the left corner
      if (done && L.kind === "pyramid" && complete && A.firepot.classes.includes(c))
        fig(ctx.sprite(A.firepot.file, frame(A.firepot, now, x * 7 + y * 3)), ox + A.firepot.dx, oy + A.firepot.dy, false);
      // palace guard (animation_draw 0x0045D140 case 0x75): drawn on the piece that shows a front picture (1163 /
      // 1176, the only palace pictures with animation frames); turned over in views 2/6, and in 0/4 at orientation
      // 1: anchor (x + 126, y + 43) (exe dx 231, dy 43 from x + 119 - 5), else (x + 114, y + 40)
      if (ph.file === "Zeus_General" && (ph.index === 1163 || ph.index === 1176) && !b.burning) {   // burning: city_draw skips animation_draw
        const flip = view === 2 || view === 6 || o === 1;
        fig(ctx.sprite(A.palace_guard.file, frame(A.palace_guard, now)),
            flip ? ox + 126 : ox + A.palace_guard.dx, oy + (flip ? 43 : A.palace_guard.dy), flip);
      }
      // a large statue being carved (p[6] = the work's start tick; sim monuments.CONAN): the exe hides the artisan and
      // the piece's +0x48 (0x005407A0 -> FUN_00430490) plays its conan phase (statue_conan.txt, anims.conan): t = the
      // piece's counter +0x60, one a tick, 0..99; the row whose distances cover t, at (x0, y0) + (x1 - x0, y1 - y0) *
      // t' / distance (C division) from the piece's draw point; image = look first + base + dir * stride / 8 + (t' %
      // frames) * stride, dir = the row's column view / 2
      const C = A.conan;
      if (C && p[6] != null && C.phases[s] && C.phases[s].length) {
        let t = ((Math.floor(ctx.tick || 0) - p[6]) % 100 + 100) % 100, r = null;
        for (const row of C.phases[s]) { if (t < row[5]) { r = row; break; } t -= row[5]; }
        const k = r && C.looks[r[4]];
        if (k) {
          const tr = (a, b) => Math.trunc((b - a) * t / r[5]);
          const idx = k.first + k.base + r[6 + (view >> 1)] * (k.stride >> 3) + (t % k.frames) * k.stride;
          fig(ctx.sprite(C.file, idx), ox + r[0] + tr(r[0], r[2]), oy + r[1] + tr(r[1], r[3]), false);
        }
      }
      // burning palace (bug 268): building_ignite lights the two 4x4 pieces (root and piece 1; the 1x1 pieces'
      // counters stay 0), the flames (city_draw -> FUN_0045A8E0, scene.js) at the piece's draw point. The exe shows
      // them on piece 1 only (oracle 1F-palacefire s_0750 / s_0960, view 0, orientation 0: 9 of 16 tiles at the
      // table offsets to the pixel, none on the root's back picture; hypothesis: drawn under its own picture)
      if (b.burning && b.key === "palace" && i === 1 && n === 4 && ctx.flames) ctx.flames(out, depth, x, ox, oy, 4, x, y);
      if (cls.anim && done && complete) {            // observatory, museum: ordinary building animation
        const a = cls.anim, f = ctx.sprite(a.file, a.start + Math.floor(now / 100) % a.count);
        if (f) out.push([depth, x, f, tl[0] + a.dx, tl[1] + a.dy]);
      }
    });
  }

  // height in pixels of a monument tile above the terrain (for walkers on terraces); 0 outside
  function heightPx(b, x, y, ctx) {
    const D = dataOf(ctx || {});
    let L = D && D.layouts[b.key];
    if (!L || !b.pieces) return 0;
    [L, b] = turned(D, L, b);
    const tx = x - b.x, ty = y - b.y;
    if (tx < 0 || ty < 0 || tx >= L.w || ty >= L.h) return 0;
    return heights(D, L, b).H[ty * L.w + tx] * D.pixels_per_height;
  }

  // the draw point [x, y] (left-corner tile in the current view, raised) and order key of the first piece of class c
  // (the sanctuary's altar 2: the immortals column, overlays.js; exe sanctuary_altar_part 0x004EA390), or null
  function piecePoint(b, c, ctx) {
    const D = dataOf(ctx || {});
    let L = D && D.layouts[b.key];
    if (!L || !b.pieces) return null;
    [L, b] = turned(D, L, b);
    const G = heights(D, L, b), i = b.pieces.findIndex(p => p[2] === c);
    if (i < 0) return null;
    const [dx, dy] = b.pieces[i], x = b.x + dx, y = b.y + dy, n = (D.classes[c] || { size: 1 }).size || 1;
    const lf = ctx.viewFoot ? ctx.viewFoot(x, y, n, n) : { lx: x, ly: y + n - 1 };
    return [ctx.tileX(lf.lx, lf.ly), ctx.tileY(lf.lx, lf.ly) - ctx.elevPx(lf.lx, lf.ly) - D.pixels_per_height * G.ph[i],
            ctx.order ? ctx.order(x, y, n, false) : x + y + 2 * (n - 1)];
  }

  // the extras tiles (class >= 1000, terrain 0x10000000) that get a step picture: map index y * N + x. The exe's image
  // grid holds only the step picture there (FUN_00521520 writes it; map_tiles_update_images skips such a tile, so no
  // ground is computed under it); ours draws the computed ground under the step (tools/step_ground_check.mjs:
  // removing that ground changes no pixel; docs/play/monuments.md 3)
  // keep(sp): only the tiles whose step picture passes (scene.js stepGround: original pictures only)
  function stepTiles(b, ctx, N, keep) {
    const D = dataOf(ctx), out = [];
    if (!D || !b.pieces) return out;
    let L = D.layouts[b.key];
    if (!L) return out;
    [L, b] = turned(D, L, b);
    const G = heights(D, L, b);
    b.pieces.forEach(p => {
      const [dx, dy, c] = p, cls = D.classes[c];
      const sp = cls && cls.ground && stepSprite(D, L, G, ctx, dx, dy, 0, false);
      if (sp && (!keep || keep(sp))) out.push((b.y + dy) * N + b.x + dx);
    });
    return out;
  }

  const api = { draw, heightPx, piecePoint, stepTiles };
  if (typeof window !== "undefined") window.Monuments = api;
  if (typeof module !== "undefined") module.exports = api;
})();
