// Play-mode scene: turns the sim's exported state into sprite draws with the original's art.
// Draw rules: docs/play/buildings.md, docs/play/walkers.md; mapping: data/play/{buildings,walkers}.json.
// Pure presentation: reads S (state.json), T (terrain.json), P.f0/f1 (frames), never game rules.
// Each draw is [depth, tiebreak, sprite, left, top]; play.js sorts and batches them.
"use strict";

// fixed per-tile random bits (the original's grid_random; ours is a hash, so variants differ from Zeus)
function tileRand(x, y) {
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return (h ^ (h >>> 16)) >>> 0;
}

const elevPx = (x, y) => (T.elev[y * N + x] || 0) * 30;

// an image of an n-tile object whose footprint starts at world tile (x, y): bottom of the image = bottom
// vertex. key = its draw-order key (order.js; default: the footprint's own anchor, Order.obj). In views 2 and 6
// the picture is mirrored (building_mirrored 0x0045DC10); overlays on it go through overlayAt.
function place(out, sp, x, y, n, key) {
  if (!sp) return null;
  const f = viewFoot(x, y, n, n), depth = key != null ? key : Order.obj(x, y, n);
  if (viewMirror()) sp = mirrored(sp);
  const left = tileX(f.ax, f.ay) - 30 * (n - 1), top = tileY(f.ax, f.ay) + 30 * n - sp.h - elevPx(f.ax, f.ay);
  out.push([depth, x, sp, left, top]);
  return [left, top];
}

// a building the exe draws as ground in pass 1 (types 2, 9, roadblock 0x7B, corral 0x86: city_draw 0x0045848C
// switch) with a top (image +0x35): its base (lower 15n + 1 rows) under every sorted picture, the top
// (building_top_draw 0x005ADF00) at its anchor like any object (docs/play/draw-order.md 2, bugs.md 203)
function placeSplit(out, sp, x, y, n) {
  if (!sp) return null;
  const tl = place(out, sp, x, y, n), e = out[out.length - 1], cut = e[2].h - 15 * n - 1;
  if (e[2].h <= 30 * n) { e[0] = Order.pass1(x, y); return tl; }   // no top (image +0x35 = 0; height is the proxy)
  const full = e[2];
  e[2] = subSprite(full, 0, 0, full.w, cut);
  out.push([Order.pass1(x, y), x, subSprite(full, 0, cut, full.w, full.h - cut), e[3], e[4] + cut]);
  return tl;
}

// a picture drawn at (dx, dy) inside a building picture of width bw placed at tl: mirrored with it in views
// 2 and 6 (the exe draws a mirrored building's extras mirrored, building_extra_sprite / animation_draw)
function overlayAt(out, depth, key, sp, tl, bw, dx, dy) {
  if (!sp) return;
  if (viewMirror()) out.push([depth, key, mirrored(sp), tl[0] + bw - dx - sp.w, tl[1] + dy]);
  else out.push([depth, key, sp, tl[0] + dx, tl[1] + dy]);
}

// a building's own orientation o (0..3, world: exe +0xAC) -> its picture in this view (shore buildings,
// big commemoratives: 0x00496CA0 / refresh 0x004953C0): F((o - view/2) & 3), F(r) = r ^ 3 in views 2 and 6
// (0x00495390 + 0x0045DC50: ((2r & 7) ^ 6) / 2), else r; the picture is then mirrored there (place())
function viewOrient(o) {
  const r = ((o || 0) - (VIEW >> 1)) & 3;
  return viewMirror() ? r ^ 3 : r;
}

// commemorative god statues (variants 10..65; exe FUN_00496CA0 case 0x77, docs/play/monuments.md 9): sanctuary tiles
// round a 1x1 (small, 3x3) or 2x2 (large, 4x4) statue at (1, 1). Facing f from the orientation o (+0xAC) and the
// view: small ((view + 2o) & 7) / 2, large ((2o - view) & 7) / 2, ^6 in views 2/6 before halving (0x0045DC50;
// oracle runs commem-*). Each piece is its own picture on its own tile, mirrored in views 2/6 (place)
function drawStatue(out, b, S) {
  const v = b.variant, god = S.god[v], large = S.large_variants.includes(v), n = large ? 4 : 3, c = large ? 2 : 1;
  const o = (b.orient || 0) & 3;
  const f = ((((large ? 2 * o - VIEW : VIEW + 2 * o) & 7) ^ (viewMirror() ? 6 : 0)) >> 1) & 3;
  let st;
  if (large) st = sprite(S.large[god][0], S.large[god][1] + f);
  else {
    const s = S.sculpture[god], sp = S.small_special[s];
    st = sp ? sprite(sp[0], sp[1] + f) : sprite(S.small[0], S.small[1] + 4 * s + f);
  }
  const ts = sprite(S.tile[0], S.tile[1]);
  for (let dy = 0; dy < n; dy++) for (let dx = 0; dx < n; dx++)
    if (!(dx >= 1 && dx <= c && dy >= 1 && dy <= c)) place(out, ts, b.x + dx, b.y + dy, 1);
  place(out, st, b.x + 1, b.y + 1, c);
}

function animFrame(a, on) {                       // building animation: wall clock, only while working
  if (!a || !on) return null;
  const ms = a.ms_per_frame || 100;
  return sprite(a.file, a.start + Math.floor(performance.now() / ms) % a.count);
}

// --- resources (zeus ids for storage bays) ---
let RES_ID = {};
function setResources(list) { RES_ID = {}; for (const r of list || []) RES_ID[r.key] = r.zeus_id; }

// granary piles (exe 0x004574C0): [[zeus id, slot]] for foods by ascending id; n = 1 if <= 400 else stock//400;
// full granary with < 8 piles: +1 for the largest stock % 400 (first on ties)
function granaryPiles(goods, g) {
  const foods = Object.entries(goods).map(([k, n]) => [RES_ID[k], n]).filter(([id, n]) => id >= 1 && id <= 8 && n > 0)
    .sort((a, b) => a[0] - b[0]);
  let total = 0, best = 0, bestRem = 0, stored = 0;
  const cnt = {};
  for (const [id, n] of foods) {
    stored += n;
    cnt[id] = n > 3200 ? 0 : n <= 400 ? 1 : Math.floor(n / 400);
    total += cnt[id];
    if (n % 400 > bestRem) { bestRem = n % 400; best = id; }
  }
  if (stored >= (g.capacity || 3200) && total < 8 && best) cnt[best]++;
  const out = [];
  for (const [id] of foods) for (let i = 0; i < cnt[id] && out.length < 8; i++) out.push([id, out.length]);
  return out;
}

// --- per-type extras of city_draw (docs/play/buildings.md 7c; data/play/buildings.json `loops`, `stock_pics`) ---
// The draw point of an n-tile picture placed at tl with height h is (tl.x, tl.y + h - 15*(n+1)).
// loops: the first entry whose condition holds (staffed; `act` = b.act, sim/export.py shore_act), a SprAmbient
// frame at point + (dx - anchor_x, dy - anchor_y)
function drawLoops(out, depth, b, list, tl, bw, bh, n) {
  if (!list || !tl || b.burning || !((b.employees || 0) > 0)) return;
  const L = list.find(e => e.when === "show" ? b.anim === "work" : e.when !== "act" || b.act === e.act);
  if (!L) return;
  const o = viewOrient(b.orient), row = L.by_orient ? L.by_orient[o] : [L.first, L.dx, L.dy];
  const k = Math.floor(performance.now() / L.ms_per_frame) % L.frames;
  const fs = sprite(L.file, row[0] + k * (L.dirs || 1) + (L.dir === "2o" ? 2 * o : 0));
  // guardpost turned over (views 2/6): the exe's anchor is x + 3*59 - 116 = x + 61, 3 px left of the exact mirror
  // (x + 64) overlayAt gives (animation_draw 0x0045D140 case 0x7C; docs/play/monuments.md 6a)
  const mdx = b.key === "guardpost" && viewMirror() ? 3 : 0;
  if (fs) overlayAt(out, depth, b.x, fs, tl, bw, row[1] - fs.ax + mdx, bh - 15 * (n + 1) + row[2] - fs.ay);
}
// stadium show (FUN_0044CD10, docs/play/buildings.md 7d): the half showing the root's own picture (S / E) draws
// list "S", the other "N"; `set` entries only on their day ((day_of_month + 1) % 6 / 2), `phase` entries follow
// one shared counter; mirrored about the picture when (view/2 + orientation) is odd (0x0044CD10 bVar5: the E / W
// pictures are the S / N ones turned over, so an "h" stadium mirrors them in views 0 and 4)
function drawShow(out, depth, b, show, list, tl, bw, bh, n, mir) {
  const day = Math.floor((P.t || 0) / 51), set = (((day % 16) + 1) % 6) >> 1, now = performance.now();
  for (const e of list) {
    if (e.set != null && e.set !== set) continue;
    const k = ((Math.floor(now / e.ms_per_frame) - (e.phase || 0)) % e.frames + e.frames) % e.frames;
    const fs = sprite(show.file, e.first + k);
    if (!fs) continue;
    const dx = e.dx - fs.ax, dy = bh - 15 * (n + 1) + e.dy - fs.ay;
    if (mir) out.push([depth, b.x, mirrored(fs), tl[0] + bw - dx - fs.w, tl[1] + dy]);   // after the half's picture (push order)
    else out.push([depth, b.x, fs, tl[0] + dx, tl[1] + dy]);
  }
}
// stock pictures (building_extra_draw 0x0044F320): by the stock of `good`, at point + (dx, dy), no anchors
function stockIndex(p, s) {
  if (p.rule === "any") return s > 0 ? 0 : null;
  if (p.rule === "ge100") return s >= 100 ? 0 : null;
  if (p.rule === "mint") return s ? Math.min(Math.max(Math.trunc((s - 50) / 50), 0), p.max) : null;
  return s >= 100 ? Math.min(Math.trunc((s - 100) / 100), p.max) : null;   // std
}
function drawStockPics(out, depth, b, list, tl, bw, bh, n, early) {
  if (!list || !tl) return;
  for (const p of list) {
    if (!!p.before_anim !== early) continue;
    const k = stockIndex(p, (b.goods || {})[p.good] || 0);
    if (k == null) continue;
    const ps = sprite(p.file, p.first + (p.reverse ? p.max - k : k));
    const [dx, dy] = p.by_orient ? p.by_orient[viewOrient(b.orient)] : (p.offsets && p.offsets[k]) || [p.dx, p.dy];
    if (ps) overlayAt(out, depth, b.x, ps, tl, bw, dx, bh - 15 * (n + 1) + dy);
  }
}

// marble quarry / black marble shop yard (city_draw case 0x31 / 0xD5 -> FUN_0045C170, docs/play/buildings.md 7c):
// while staffed and not burning, stock 0 -> the idle figure (figures[grid_random & 1], dir 3), stock s >= 100 -> the
// stonecutter at the block, cutters[s // 100 - 1]; top-left = draw point + (dx - ax, dy - ay)
function drawYard(out, depth, b, Y, tl, bw, bh, n) {
  if (b.burning || !((b.employees || 0) > 0)) return;
  const s = (b.goods || {})[Y.good] || 0;
  let f, dir, dx, dy;
  if (s === 0) ({ dir, dx, dy } = Y.idle), f = Y.idle.figures[tileRand(b.x, b.y) & 1];
  else {
    const c = Y.cutters[Math.min(Math.floor(s / 100), 8) - 1];   // 1..99 (never in the sim) and < 0: no picture
    if (!c) return;
    f = c; dir = c.dir; dx = c.dx; dy = c.dy;
  }
  const k = Math.floor(performance.now() / f.ms_per_frame) % f.frames;
  const fs = sprite(f.file, f.first + k * f.dirs + dir);
  if (fs) overlayAt(out, depth, b.x, fs, tl, bw, dx - fs.ax, bh - 15 * (n + 1) + dy - fs.ay);
}

// --- buildings ---
function drawBuilding(out, b, m) {
  const w = b.w || b.size || 1, h = b.h || b.size || 1;
  const depth = Order.obj(b.x, b.y, w, h);        // its anchor cell; extras pushed after it (draw-order.md)
  // exe rule, computed by the sim (economy.anim_state): "work" / "idle" (stalled: idle worker) / null
  const state = b.anim !== undefined ? b.anim : (b.employees || 0) > 0 ? "work" : null;
  const working = state === "work";
  if (b.kind === "house" && m.levels && m.kind !== "elite_house") {
    let sp;
    if (!b.occupants && m.vacant) sp = sprite(m.vacant.file || m.file, m.vacant.base);
    else {
      const L = m.levels[Math.min(b.level, m.levels.length - 1)];
      sp = sprite(L.file || m.file, L.variants[tileRand(b.x, b.y) & 1]);
    }
    return place(out, sp, b.x, b.y, 2, depth);
  }
  if (m.kind === "elite_house") {
    const L = m.levels.find(l => l.level === b.level) || m.levels[0];
    // quadrant k (0..3) shows image T[k'] (0x0063B9E8 = [2, random bit, 3, 4]) at Q[(k + view/2) & 3]
    // (0x0063B988); k' swaps 1 and 3 in views 2 and 6 (elite_house_place_sprites 0x004FECF0)
    const T4 = [2, tileRand(b.x, b.y) & 1, 3, 4], Q = [[2, 2], [0, 2], [0, 0], [2, 0]];
    for (let k = 0; k < 4; k++) {
      const [dx, dy] = Q[(k + (VIEW >> 1)) & 3], kk = viewMirror() && (k & 1) ? k ^ 2 : k;
      const sp = sprite(L.file || m.file, L.first + T4[kk]);
      place(out, sp, b.x + dx, b.y + dy, 2);       // each quadrant is its own anchor
    }
    return;
  }
  if (m.kind === "storage" && m.root) {
    // 1x1 pieces, each its own anchor (the exe places root + bays as separate pictures)
    const rs = sprite(m.root.file || m.file, m.root.base), rk = Order.obj(b.x, b.y, 1);
    const rtl = place(out, rs, b.x, b.y, 1, rk);
    if (rs) drawLoops(out, rk, b, m.loops, rtl, rs.w, rs.h, 1);   // storehouse / dock house / trading post worker
    const bi = m.bay_images, loads = [];        // fill bays of 400 units from the totals (presentation only)
    for (const [g, n] of Object.entries(b.goods || {})) for (let left = n; left > 0; left -= 400) loads.push([g, Math.min(400, left)]);
    let k = 0;
    for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) {
      if (!dx && !dy) continue;
      const ld = loads[k++];
      let sp = null;
      if (ld) {
        const id = RES_ID[ld[0]], first = bi.goods_first[id], pos = bi.poseidon_goods_first && bi.poseidon_goods_first[id];
        const band = ld[1] < 200 ? 0 : ld[1] < 300 ? 1 : ld[1] < 400 ? 2 : 3;
        if (first != null) sp = sprite(bi.file, first + (id === 19 ? 0 : band));
        else if (pos) sp = sprite(pos[0], pos[1] + band);
      }
      place(out, sp || sprite(bi.file, bi.empty), b.x + dx, b.y + dy, 1);
    }
    if (m.pier && b.pier) {                     // dock: the 2x2 pier half on the water, image by orientation (bugs.md 131)
      const [px, py] = b.pier;
      const ps = sprite(m.pier.file, m.pier.first + viewOrient(b.orient));
      const pk = Order.obj(px, py, 2), ptl = place(out, ps, px, py, 2, pk);
      if (ps) drawLoops(out, pk, b, m.pier_loops, ptl, ps.w, ps.h, 2);
    }
    return;
  }
  if (m.kind === "agora") return;               // its road strip is drawn by drawAgoraRoads
  if (m.kind === "gate" && w !== h) return drawGatehouse(out, b, m, w > h ? 1 : 0, VIEW);
  if (m.parts && w !== h) {                     // stadium: one image per 5x5 half (exe FUN_005AFB40)
    const n = m.img_tiles || 5;
    // images per view (table 0x005E4958 + (view/2 + 4o)*0x38): the two halves' pictures swap in views 4, 6
    // (o = 0, v) or 2, 4 (o = 1, h)
    const hz = w > h, P = m.parts[hz ? "h" : "v"], sw = hz ? VIEW === 2 || VIEW === 4 : VIEW >= 4;
    P.forEach(([dx, dy], i) => {
      const j = sw ? P.length - 1 - i : i, sp = sprite(m.parts.file, P[j][2]), d = Order.obj(b.x + dx, b.y + dy, n);
      const tl = place(out, sp, b.x + dx, b.y + dy, n, d);
      if (m.show && tl && b.anim === "work" && !b.burning) drawShow(out, d, b, m.show, m.show[j ? "N" : "S"], tl, sp.w, sp.h, n, viewMirror() !== hz);
    });
    return;
  }
  if (m.statues && b.variant >= 10) return drawStatue(out, b, m.statues);   // god statue commemoratives
  let base = m.base != null ? m.base : m.front;
  if (m.variants) base = m.variants[tileRand(b.x, b.y) % m.variants.length];
  if (m.stages && b.growth != null) base = m.stages.first + Math.min(m.stages.count - 1, Math.floor(b.growth / 20));
  const vs = m.variant_stride && b.variant ? m.variant_stride * b.variant : 0;    // water park variant (bugs.md 136)
  base += vs;
  if (m.orient_stride) base += m.orient_stride * viewOrient(b.orient);   // shore buildings: water side (bugs.md 131), per view
  const n = m.img_tiles || w;
  const sp = sprite(m.file, base);
  if (m.corral && b.corral) {                   // horse ranch: its 4x4 corral (exe building 0x86, bugs.md 134)
    const [cx, cy] = b.corral;
    placeSplit(out, sprite(m.corral.file, m.corral.base), cx, cy, 4);   // base in pass 1, fences at its anchor; horses on it drawn late (order.js defer)
  }
  const tl = place(out, sp, b.x, b.y, n, depth);
  if (!tl) return;
  if (m.crop) {                                 // farms: 5 crop patches by growth
    let p = Math.floor(Math.min(b.growth || 0, 100) / 4);
    const stage = [];
    for (let i = 0; i < 5; i++) { stage.push(Math.min(5, p)); p = Math.max(0, p - 5); }
    for (const i of m.crop.draw_order) {
      const [dx, dy] = m.crop.patch_offsets[i];
      const cs = sprite(m.crop.file, m.crop.first + stage[i]);
      overlayAt(out, depth, b.x, cs, tl, sp.w, 60 + 30 * dx, 55 + 15 * dy - (cs.h - 30));
    }
  }
  const stocked = b.stocked != null ? b.stocked : b.goods && Object.keys(b.goods).length > 0;
  if (m.stock_overlay && m.stock_overlay.dx != null && stocked) {
    const o = m.stock_overlay, os = sprite(o.file, o.index);
    overlayAt(out, depth, b.x, os, tl, sp.w, o.dx, o.dy);
  }
  // exe city_draw per-type extra animations (0x0045B500 fish pond, 0x0045B690.. stall vendors; bugs.md 130, 135): a
  // SprAmbient loop at the draw point (base_left, base_top + h - 15*(n+1)) + (x - anchor_x, y - anchor_y)
  const ov = m.overlay || (m.vendor && stocked && (b.employees || 0) > 0 ? m.vendor : null);
  if (ov) {
    const k = Math.floor(performance.now() / ov.ms_per_frame) % ov.frames, vs = sprite(ov.file, ov.first + k);
    overlayAt(out, depth, b.x, vs, tl, sp.w, ov.x - vs.ax, sp.h - 15 * (n + 1) + ov.y - vs.ay);
  }
  if (m.goods && m.goods.slots && b.goods) {    // granary: food piles in the 8 roof openings (exe 0x004574C0)
    const g = m.goods, cx = tl[0], cy = tl[1] + sp.h - 75;   // cell point = left tile of the 4x4
    granaryPiles(b.goods, g).forEach(([id, k]) => {
      const ps = g.poseidon[id] ? sprite(g.poseidon[id][0], g.poseidon[id][1]) : sprite(g.file, g.first + id - 1);
      const [ax, ay] = g.adjust[id] || [0, 0];
      overlayAt(out, depth, b.x, ps, tl, sp.w, cx - tl[0] + g.slots[k][0] + ax, cy - tl[1] + g.slots[k][1] + ay);
    });
  }
  drawStockPics(out, depth, b, m.stock_pics, tl, sp.w, sp.h, n, true);   // quarry: before the work animation
  if (m.yard) drawYard(out, depth, b, m.yard, tl, sp.w, sp.h, n);
  const fr = animFrame(vs && m.anim ? { ...m.anim, start: m.anim.start + vs } : m.anim, working || m.anim && b.kind === "monument");
  if (fr) overlayAt(out, depth, b.x, fr, tl, sp.w, m.anim.dx, m.anim.dy);
  if (state === "idle" && m.idle) {             // exe 0x0044EAB0: idle worker in front instead of the work animation
    const i = m.idle, f = i.figures[tileRand(b.x, b.y) & 1];
    const k = Math.floor(performance.now() / f.ms_per_frame) % f.frames;
    const fs = sprite(f.file, f.first + k * f.dirs + i.dir);
    overlayAt(out, depth, b.x, fs, tl, sp.w, ((sp.w + 1) >> 1) + i.dx - fs.ax, sp.h - 15 * (n + 1) + i.dy - fs.ay);   // draw point (oracle 10-28)
  }
  drawLoops(out, depth, b, m.loops, tl, sp.w, sp.h, n);       // guardpost sentry, wharf/quay workers
  if (b.hero != null && window.Heroes) Heroes.hallExtra(out, depth, b, tl, sp.w, sp.h - 15 * (n + 1));   // statue (heroes.js)
  drawStockPics(out, depth, b, m.stock_pics, tl, sp.w, sp.h, n, false);
}

// gatehouse (exe FUN_004E4FA0, buildings.md §5 "Gatehouse"): four pieces, [size, a, b] (table 0x0063A848) at
// (x+b, y+a) in orientation 0 (v, 2x5) or (x+a, y+b) in 1 (h, 5x2); draw slot k has image group GATE_IMG[k]
// (0x0063A780: tower 138, passage back 107, passage front 112, tower 138) on piece GATE_ORDER[o+view][k]
// (0x0063A7C8); +1 image when o+view is 0, 3, 4 or 7, the other way round in views 2 and 6. Old saves'
// 2x2 gatehouses (w == h) draw the generic way. Each piece is its own anchor. Then FUN_004E5730 (called at every
// anchor of the gatehouse, so in effect after the front-most one; docs/play/draw-order.md 6) draws slot 2's arch
// overlay SPR_GATE_OVERLAY (775 + alt) at the slot-2 tile + (0, -72) / (7, -82) (oracle gate-walk v0: 0 px) and
// slot 3's tower again: a walker in the passage (drawn on its own cell) is under the arch (bugs.md 167).
const GATE_PIECES = [[2, 0, 0], [1, 2, 0], [1, 2, 1], [2, 3, 0]];
const GATE_ORDER = [[0, 1, 2, 3], [0, 1, 2, 3], [0, 2, 1, 3], [3, 1, 2, 0], [3, 2, 1, 0], [3, 2, 1, 0], [3, 1, 2, 0], [0, 2, 1, 3]];
function drawGatehouse(out, b, m, o, view) {
  const v = (o + view) & 7, img = [m.base, m.back, m.front, m.base];
  let alt = [0, 3, 4, 7].includes(v) ? 1 : 0;
  if (view === 2 || view === 6) alt = 1 - alt;
  let last = -Infinity;
  const at = GATE_ORDER[v].map((pi, k) => {
    const [n, a, bb] = GATE_PIECES[pi];
    const px = b.x + (o === 0 ? bb : a), py = b.y + (o === 0 ? a : bb), key = Order.obj(px, py, n);
    place(out, sprite(m.file, img[k] + alt), px, py, n, key);
    last = Math.max(last, key);
    return [px, py, n];
  });
  const os = m.overlay != null && sprite(m.file, m.overlay + alt);
  if (os) {
    const [px, py] = at[2], [dx, dy] = alt ? [0, -72] : [7, -82], top = tileY(px, py) - elevPx(px, py) + dy;
    if (viewMirror()) out.push([last, b.x, mirrored(os), tileX(px, py) + 58 - dx - os.w, top]);
    else out.push([last, b.x, os, tileX(px, py) + dx, top]);
  }
  const [tx, ty, tn] = at[3];
  place(out, sprite(m.file, img[3] + alt), tx, ty, tn, last);
}

function drawAgoraRoads(out, b, m, stalls) {
  const w = b.w || 1, h = b.h || 1;
  for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) {
    const x = b.x + dx, y = b.y + dy;
    if (stalls.has(y * N + x)) continue;
    const sp = sprite(m.file, m.road_tiles[tileRand(x, y) % m.road_tiles.length]);
    place(out, sp, x, y, 1, Order.cell(x, y, Order.GROUND));   // flat strip: ground of its cell
  }
}

// --- fire (city_draw 0x00458170 -> FUN_0045A8E0; docs/play/buildings.md "Fire") ---
// A burning part's picture stays; over it, per tile of its footprint (pixel offsets by size from its draw point:
// data/play/buildings.json ruin.flames, tables 0x005F5D08..), a flame loop picked by grid_random % 10 (two of ten
// tiles none) at draw point + (dx + 20 - anchor_x, dy + 20 - anchor_y), never mirrored. Ours: grid_random is a
// hash (tileRand), each tile's loop starts at its own frame (the exe's per-tile counter grid 0x00CB4B08).
function drawFlames(out, depth, key, ox, oy, n, x, y) {
  const F = ((MAP.buildings || {}).ruin || {}).flames;
  if (!F) return;
  const offs = F.offsets[n] || F.offsets[1], now = performance.now();
  offs.forEach(([dx, dy]) => {
    const r = tileRand(x * 64 + dx, y * 64 + dy), c = F.choices[r % 10];
    if (!c) return;
    const sp = sprite(c.file, c.first + (Math.floor(now / c.ms_per_frame) + (r >>> 8)) % c.frames);
    if (sp) out.push([depth, key, sp, ox + dx + 20 - sp.ax, oy + dy + 20 - sp.ay]);
  });
}
// the draw point of an n-tile part whose min tile is (x, y): its left-corner tile's box in this view
function partFlames(out, x, y, n) {
  const f = viewFoot(x, y, n, n);
  const ox = tileX(f.ax, f.ay) - 30 * (n - 1), oy = tileY(f.ax, f.ay) + 15 * (n - 1) - elevPx(f.ax, f.ay);
  drawFlames(out, Order.obj(x, y, n), x, ox, oy, n, x, y);
}
// every burning part of b (the exe's part records): storage (storehouse root + 1x1 bays) per tile, the stadium per
// 5x5 half, the horse ranch's house and 4x4 corral (oracle 1F-ranchburn: 9 + 9 + 16 flame figures), a stall of a
// burning agora (export: the agora's counter; the agora root has no tiles), else the footprint (a ruin: 1).
// Monuments draw their own (monuments.js: the palace's two 4x4 pieces).
function buildingFlames(out, b, m) {
  if (!b.burning) return;
  const w = b.w || b.size || 1, h = b.h || b.size || 1;
  if (b.corral) partFlames(out, b.corral[0], b.corral[1], 4);
  if (m && m.kind === "storage" && m.root) {
    for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) partFlames(out, b.x + dx, b.y + dy, 1);
  } else if (m && m.parts && w !== h) {
    const n = m.img_tiles || 5;
    for (const [dx, dy] of m.parts[w > h ? "h" : "v"]) partFlames(out, b.x + dx, b.y + dy, n);
  } else if (w === h) partFlames(out, b.x, b.y, w);
}

// monuments (sanctuaries, pyramids, palace): piece by piece, viewer/play/monuments.js
const MCTX = { flames: (out, depth, key, ox, oy, n, x, y) => drawFlames(out, depth, key, ox, oy, n, x, y), sprite: (f, i) => sprite(f, i), tileX: (x, y) => tileX(x, y), tileY: (x, y) => tileY(x, y),
               elevPx: (x, y) => elevPx(x, y), rand: (x, y) => tileRand(x, y),
               viewFoot: (x, y, w, h) => viewFoot(x, y, w, h), get view() { return VIEW; }, get tick() { return P.t; },
               // draw-order key of a piece (order.js): its anchor cell; flat pictures are ground of that cell
               order: (x, y, n, flat) => { const f = viewFoot(x, y, n, n); return Order.cell(f.lx, f.ly, flat ? Order.GROUND : Order.OBJECT); },
               get mirror() { return viewMirror() ? mirrored : null; }, flip: sp => mirrored(sp) };

// monument step tiles (Monuments.stepTiles: extras with a step picture): the exe's image grid holds only the step picture
// there (FUN_00521520), no ground (map_tiles_update_images 0x0051F450 skips the tile), so the terrain batch leaves those
// tiles out (play.js buildTerrain, stepGround). The set depends on the monuments' placement (and a pyramid's stages):
// the terrain batch is rebuilt when that changes (bugs.md 400). Ours (bug 441, 11-03): a hi-res step picture (sprite
// with uw: the Remacri sets) keeps the ground under it: the upscale erodes the picture's diamond edge, which at 1x
// interlocks with its neighbours', so with nothing behind it showed a dotted black line along every step edge (the
// original pictures leave the exe's few single-pixel holes only; buildTerrain runs again when a hi-res set changes)
let monStepKey = null;
// the monuments (and pyramid levels) the step tiles come from; null before the buildings are known
function monStepKeyNow() {
  if (typeof S === "undefined" || !S || !S.buildings || !window.Monuments) return null;
  let k = "";
  for (const b of S.buildings) if (b.kind === "monument" && b.pieces)
    k += `${b.key},${b.x},${b.y},${b.orient || 0}${b.key.startsWith("pyramid") ? ":" + b.pieces.map(p => p[4]).join(".") : ""}|`;
  return k;
}
function stepGround() {
  const out = new Set();
  monStepKey = monStepKeyNow();                   // what this terrain build left out (monumentStepsChanged)
  if (monStepKey === null) return out;
  for (const b of S.buildings) if (b.kind === "monument" && b.pieces)
    for (const i of Monuments.stepTiles(b, MCTX, N, sp => !sp.uw)) out.add(i);
  return out;
}
// the terrain again when the step tiles changed since it was built, also when it was built before the buildings
// were known (page load: the ground under the steps showed until the next terrain poll, bugs.md 463)
function monumentStepsChanged() {
  const k = monStepKeyNow();
  if (k === null || k === monStepKey) return;
  if (typeof T !== "undefined" && T && typeof buildTerrain === "function") buildTerrain();
}

function sceneBuildings(out, fallback) {
  const BM = MAP.buildings || {};
  try { monumentStepsChanged(); } catch (e) { sceneError(e, "monument steps"); }
  const stalls = new Set();
  for (const b of S.buildings) if (b.kind === "stall") {
    const w = b.w || b.size || 1, h = b.h || b.size || 1;
    for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) stalls.add((b.y + dy) * N + b.x + dx);
  }
  for (const b of S.buildings) try {
    if (b.kind === "road" || b.kind === "animal" || b.key === "avenue" || b.key === "boulevard" || b.key === "gardens") continue;
    if (window.Overlays && Overlays.hidden(b)) continue;      // map overlay: drawn flat (overlays.js)
    if (window.clearedBuilding && clearedBuilding(b)) continue; // just cleared, the snapshot not here yet (build.js)
    if (b.kind === "monument" && b.pieces && window.Monuments) { Monuments.draw(out, b, MCTX); continue; }
    const m = BM[b.key];
    if (m && m.kind === "agora") { drawAgoraRoads(out, b, m, stalls); continue; }
    if (m && (m.base != null || m.front != null || m.levels || m.root || m.variants)) drawBuilding(out, b, m);
    else fallback(out, b);
    if (b.burning && m && m.kind !== "agora" && m.kind !== "gate") buildingFlames(out, b, m);
  } catch (e) { sceneError(e, b.key); }
}

// one bad building/walker is skipped and reported once per key, the rest of the frame draws
const sceneErrors = new Set();
function sceneError(e, what) {
  if (sceneErrors.has(what)) return;
  sceneErrors.add(what);
  console.error(`scene: ${what}:`, e);
  if (typeof frameErrors !== "undefined") frameErrors++;
}

// --- roads: kind by desirability, image by the 8-neighbour pattern tables (into the terrain layer) ---
function roadSprite(x, y) {
  const r = MAP.buildings && MAP.buildings.road;
  if (!r) return null;
  const d = T.des ? T.des[y * N + x] : 0;
  const kind = d < 0 ? r.kinds[0] : d < 16 ? r.kinds[1] : d < 30 ? r.kinds[2] : r.kinds[3];
  if (!kind.table) return sprite(kind.file || r.file, kind.first + tileRand(x, y) % kind.count);
  const pv = typeof Build !== "undefined" && Build.roadPreview && Build.roadPreview.view === VIEW && Build.roadPreview.roads;
  const isRoad = (xx, yy) => xx >= 0 && yy >= 0 && xx < N && yy < N && (!!T.road[yy * N + xx] || !!(pv && pv.has(yy * N + xx)));
  const nb = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]].map(([dx, dy]) => isRoad(x + dx, y + dy));
  for (const [pat, off, offs] of r[kind.table]) {
    let ok = true;
    for (let i = 0; i < 8 && ok; i++) ok = pat[i] === "." || (pat[i] === "1") === nb[i];
    if (ok) return sprite(kind.file || r.file, kind.first + (offs ? offs[VIEW >> 1] : off));   // column view/2 (FUN_004A6920)
  }
  return null;
}

// --- walkers ---
const DIR_DELTA = { "0,-1": 0, "1,-1": 1, "1,0": 2, "1,1": 3, "0,1": 4, "-1,1": 5, "-1,0": 6, "-1,-1": 7 };
const lastDir = {};

function blockIndex(blk, dir, fr) {
  if (blk.stride_frame) return blk.start + 1 + (blk.stride_dir || 2) * dir + blk.stride_frame * (fr % (blk.frames || 1));
  const frames = blk.frames || 1, dirs = blk.dirs || 8;
  return blk.start + (fr % frames) * dirs + (dirs > 1 ? dir : 0);
}

function roleOf(WM, role, good) {               // resolves "by good" roles (trainee, buyer)
  if (good && WM[role + ":" + good]) return WM[role + ":" + good];   // sanctuary troops: rabble:amazon, hoplite:ares
  let m = WM[role];
  if (m && m.by === "good") m = WM[(m.map && m.map[good]) || m.fallback_role];
  return m;
}

// screen spot and draw-order key of a walker at fractional tile (fx, fy); opts for Order.walker (lifted, water,
// rank). The key is the exe's: its tile's cell, or 2 / 4 rows later (docs/play/draw-order.md 3.7, 5).
const BOATS = new Set(["ship", "boat", "trireme"]);      // figure_on_water (0x004D7210)
// figure types 1 immigrant, 4 cart, 0xD horseman (+ ox team 0x1C, enemy cavalry 0x2A, gods, monsters, heroes):
// figure_type_on_tile 0x0045DAF0, the tufts of the tile in front are not drawn over them (Order.topHidden)
const BIG = new Set(["immigrant", "cart", "horseman"]);
function walkerSpot(fx, fy, opts) {
  const ti = Math.round(fy) * N + Math.round(fx);
  const cx = tileX(fx, fy) + 29;
  let cy = tileY(fx, fy) + 15 - (T.elev[ti] || 0) * 30;
  // on a monument (artisans on sanctuary terraces): the tile's built height (grid 0x008E01FA, docs/play/monuments.md 3)
  const mb = buildingAt(Math.round(fx), Math.round(fy));
  if (mb && mb.kind === "monument" && mb.pieces && window.Monuments) cy -= Monuments.heightPx(mb, Math.round(fx), Math.round(fy), MCTX);
  return [Order.walker(fx, fy, opts), cx, cy];
}
// A figure's own picture (walker_draw 0x0044FEF0, bugs.md 251, docs/play/walkers.md "Position"): walkerSpot's point
// (the tile point + (29, 15) + the walk table) + (2, rise), rise 10, or the road term of roadRise for the types that
// have one; + 8 / + 4 on a quarried marble tile (terrain 0x20000, regrowth 0 / 100: terrain.json `sink`). Extra
// pictures (a cart's cargo, the ox train's trailer, a trireme's crew) hang from the plain point: (-2, -10) from this.
// Checked: tools/e1_figure_check.py on re/oracle/runs/1E-figs and 1D-walker (pictures at the rule, none elsewhere).
let SINK = { T: null, m: null };
function figureSpot(fx, fy, opts, rise = 10) {
  const r = walkerSpot(fx, fy, opts);
  if (SINK.T !== T) SINK = { T, m: new Map((T && T.sink) || []) };
  r[1] += 2;
  r[2] += rise + (SINK.m.get(Math.round(fy) * N + Math.round(fx)) || 0);
  return r;
}
// walker_draw's road term for figure types 1, 0xB, 0xC, 0xD, 0x28, 0x29, 0x2A, 0x37, 0x3B (immigrant, rabble, hoplite,
// horseman, enemy archer / infantry / cavalry, woodcutter, wolf): the previous tile's road bit (terrain 0x40) against
// +0x41 (the current tile's, set on entering it, FUN_004D7580): both road 17, both not 5, else ROAD_T[p] (from a
// field tile) / ROAD_T[15 - p] (from a road) + 10, p = tile progress (the tile changes at 8). Seen in 1E-figs shots
// (woodcutters at 7, 11, 17).
const ROAD_RISE = /^(immigrant|rabble|hoplite|horseman|enemy_(archer|infantry|cavalry)(_\d+)?|woodcutter|wolf)$/;
const ROAD_T = [1, 2, 3, 3, 4, 5, 6, 7, -5, -5, -4, -3, -2, -1, -1, 0];
const roadMem = new Map();                           // id -> [step origin x, y, the one before x, y]
function roadAt(x, y) { return x >= 0 && y >= 0 && x < N && y < N && T.road && T.road[y * N + x] ? 1 : 0; }
function roadRise(id, x0, y0, x1, y1, kk, moving) {
  let m = roadMem.get(id);
  if (!m) roadMem.set(id, m = [x0, y0, x0, y0]);
  else if (m[0] !== x0 || m[1] !== y0) { m[2] = m[0]; m[3] = m[1]; m[0] = x0; m[1] = y0; }
  let p = moving ? Math.round(kk * 15) : 0;
  const late = p >= 8;                               // on the step's new tile
  if (!p) p = 15;                                    // standing, or the step's start: the previous step's end
  const a = late ? roadAt(x0, y0) : roadAt(m[2], m[3]), b = late ? roadAt(x1, y1) : roadAt(x0, y0);
  if (a === b) return b ? 17 : 5;
  return ROAD_T[a ? 15 - p : p] + 10;
}

// agora buyer's assistants (presentation only, docs/play/walkers.md "Followers"): frame field 7 = how many;
// they appear at the storage where the loads were taken and walk in single file one tile apart along the
// tiles the buyer walked since then (trails[id], newest first).
const trails = {};
let trailSeen = new Set();
// the tiles walker `id` walked lately (newest first), updated with its current step target (x0, y0)
function trailOf(id, x0, y0) {
  trailSeen.add(id);
  const t = trails[id] || (trails[id] = [[x0, y0]]);
  const back = t.findIndex(p => p[0] === x0 && p[1] === y0);
  if (back > 0) t.splice(0, back);                       // replay scrubbed backwards
  else if (back < 0) { t.unshift([x0, y0]); if (t.length > 10) t.length = 10; }
  return t;
}
// the spot u tiles (fractional) behind the leader along its trail: the leader moves from t[1] to t[0] over
// its step (kk); u = j puts follower j on t[j+1] -> t[j] at the same kk (agora followers, bugs.md 58)
// back: [dx, dy] a tile further back past the trail's oldest point (heavy carts; ours: a trail seen too short, e.g.
// after a reload or a cart that has not moved yet, lays the followers straight back instead of on the leader's tile)
function trailSpot(t, u, kk, key, back) {
  let s = 0, f = kk - u;                          // segment s: t[s+1] -> t[s], fraction f
  while (f < 0) { s++; f += 1; }
  const at = i => {
    if (i < t.length || !back) return t[Math.min(i, t.length - 1)];
    const L = t[t.length - 1], k = i - t.length + 1;
    return [L[0] + back[0] * k, L[1] + back[1] * k];
  };
  const a = at(s + 1), b = at(s);
  const fx = a[0] + (b[0] - a[0]) * f, fy = a[1] + (b[1] - a[1]) * f;
  const dx = Math.sign(b[0] - a[0]), dy = Math.sign(b[1] - a[1]);
  if (dx || dy) lastDir[key] = DIR_DELTA[`${dx},${dy}`];
  return [fx, fy, lastDir[key] != null ? viewDir(lastDir[key]) : 3, !!(dx || dy)];
}
// the trail tiles behind a follower's step (trailSpot's segment t[s+1] -> t[s]): t[s+2], t[s+3], .. newest first,
// as rampPath's `back`; null when the trail does not reach that far (a new trail: the straight-walk formula)
function trailBack(t, u, kk) {
  let s = 0, f = kk - u;
  while (f < 0) { s++; f += 1; }
  return t.length > s + 3 ? t.slice(s + 2, s + 8) : null;
}
// ox pair on a ramp (exe 0x004D7580 on entering a tile, shown while slope_timer runs, about one tile; figure_oxcart
// 0x004C3680 action 6 draws 0x6606 = group_5 while slope_target != 0, 0x6607 = group_6 otherwise): +1 up, -1 down,
// 0 flat. wd = world heading. Tile bits: 0x400 ramp, 0x800000 (cliff ramp), 0x10000000.
const DIR_STEP = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];
// a follower (mode 2: ox pairs, trailers; FUN_004D7340) on a long ramp, from the tiles it walked (prevs: the tiles
// behind its current tile (x, y), newest first; n = counts since it entered (x, y)): k = counts since it entered the
// pair's first tile (the slope timer 30 runs from there: the offset 1 px a count up to 29, the slope picture while
// k < 30), down = the direction decided on that tile (null: none). Oracle 1F-ox: the ox pair that turns on the
// pair's second tile (133, 113) keeps counting 23..29 and shows the plain picture from k = 30 on the same tile.
function followerRun(x, y, n, prevs, nx, ny) {
  const ok = (a, b) => a >= 0 && b >= 0 && a < N && b < N;
  const el = (a, b) => ok(a, b) ? (T.elev[b * N + a] || 0) : 0, fl = (a, b) => ok(a, b) ? T.flags[b * N + a] : 0;
  const long = t => !!t && (fl(t[0], t[1]) & 0x400) && (fl(t[0], t[1]) & 0x800000);
  let r = 1;
  while (r < 16 && long(prevs[r - 1])) r++;
  const t1 = r % 2 ? [x, y] : prevs[0], t0 = (r % 2 ? prevs[0] : prevs[1]) || t1;
  const [ax, ay] = r % 2 ? [nx, ny] : [Math.sign(t1[0] - t0[0]), Math.sign(t1[1] - t0[1])];
  const e1 = el(t1[0], t1[1]), ep = el(t0[0], t0[1]), en = el(t1[0] + 2 * ax, t1[1] + 2 * ay);
  const down = e1 < ep ? true : e1 < en ? false : ep < e1 ? true : en < e1 ? false : null;
  return { k: r % 2 ? n : 15 + n, down };
}
function oxSlope(px, py, wd, back = null) {
  const x = Math.round(px), y = Math.round(py);
  if (wd == null || x < 0 || y < 0 || x >= N || y >= N) return 0;
  if (back) {                                     // the exe's timer along the path walked (followerRun)
    const [dx, dy] = DIR_STEP[wd & 7];
    const from = (q, c) => c > 0 ? Math.floor(q + 1e-6) : c < 0 ? Math.ceil(q - 1e-6) : Math.round(q);
    const sx = from(px, dx), sy = from(py, dy), p = Math.round(Math.abs(dx ? px - sx : py - sy) * 15e4) / 1e4;
    const cx = p >= 8 ? sx + dx : sx, cy = p >= 8 ? sy + dy : sy, f = T.flags[cy * N + cx];
    if (cx >= 0 && cy >= 0 && cx < N && cy < N && (f & 0x400) && (f & 0x800000)) {
      const L = followerRun(cx, cy, p >= 8 ? p - 7 : p + 8, p >= 8 ? [[sx, sy], ...back] : back, dx, dy);
      return L.k >= 30 || L.down == null ? 0 : L.down ? -1 : 1;
    }
  }
  const f = T.flags[y * N + x], [dx, dy] = DIR_STEP[wd & 7];
  if (!(f & 0x400) && !(f & 0x10000000)) return 0;
  const el = (a, b) => (a < 0 || b < 0 || a >= N || b >= N) ? 0 : (T.elev[b * N + a] || 0);
  const cliff = (f & 0x400) && (f & 0x800000);    // this branch looks 2 tiles ahead (0x004D78ED: offset*2)
  const e = el(x, y), ep = el(x - dx, y - dy), en = cliff ? el(x + 2 * dx, y + 2 * dy) : el(x + dx, y + dy);
  if (e < ep) return -1;                          // target 0
  if (e < en) return 1;                           // target 0x1E / 0x23
  if (cliff) {                                    // and also turns on a lower neighbour
    if (ep < e) return -1;
    if (en < e) return 1;
  }
  return 0;
}
// a walker's lift on a ramp, px (figure +0x78 slope_offset, walker_draw 0x0044FEF0: y - slope_offset), plus the exe's
// elevation tile against walkerSpot's rounded one. Read from the exe and checked tick by tick against oracle dumps
// (tools/e1_ramp_check.py, re/oracle/runs/e1-ramps; bugs.md 211, docs/play/walkers.md "Lift on ramps"):
// - a step from tile S to S + d is 15 progress counts (+0x39); the tile changes at count 8 (figure_change_tile). The
//   movers differ in the order: figure_route_walk 0x004D7BD0 changes the tile, then steps (one slope step done on
//   entry: mode 0); figure_roam_steps 0x004D69B0 and FUN_004D7110 (roamers, wanderers) step, then change (none:
//   mode 1); FUN_004D7340 (followers: ox pairs, trailers, vendor assistants) changes, then moves the offset 1 px a
//   call (mode 2). So n = steps since entry = p - 7 (p >= 8, the new tile) or p + 8 (p < 8, still S), - 1 in mode 1;
// - on entering (FUN_004D7580): a single ramp (0x400 or 0x10000000, not long): previous tile higher -> timer 15,
//   offset 30, target 0; next tile higher -> timer 15, offset 0, target 30; else 0. A long ramp (0x400 + 0x800000, two
//   tiles at the low elevation) only while its timer is 0 (so the second tile of a pair keeps the first's): timer 30;
//   previous higher -> 35 -> 0; else the tile 2 ahead higher -> 0 -> 35; else previous lower -> down; else 2 ahead
//   lower -> up. Any other tile: offset 0;
// - figure_fine_step 0x004D94F0: while the timer runs, offset +-1 toward the target, +-1 more on a ramp tile; the
//   step that ends the timer changes nothing. So single up 2 min(n, 14), down 30 - 2 min(n, 14); long up
//   min(35, 2 min(K, 29)), down max(0, 35 - 2 min(K, 29)), K = n on the pair's first tile, 15 + n on its second
//   (consecutive pairs alternate); mode 2 1 px a step instead of 2.
// Ours from the drawn position (tile point to tile point), heading wd (world) and nd, the route's next step after this
// one (the exe's route[route_step] on entering at count 8; a roamer's: straight on).
// With `back` (the tiles walked before the step's origin, newest first: rampPath) a route walker or a roamer (modes 0
// and 1) gets the exe's state machine replayed over its last tiles instead (rampReplay): its slope state carries over
// turns and U-turns as the exe's does (FUN_004D7580 on each entry, figure_fine_step 0x004D94F0 15 times a tile).
function rampLift(fx, fy, wd, mode = 0, nd = wd, back = null) {
  if (wd == null || !T) return 0;
  if (back && mode !== 2) return rampReplay(fx, fy, wd, mode, nd, back);
  const [dx, dy] = DIR_STEP[wd & 7], [nx, ny] = DIR_STEP[(nd == null ? wd : nd) & 7];
  const from = (q, c) => c > 0 ? Math.floor(q + 1e-6) : c < 0 ? Math.ceil(q - 1e-6) : Math.round(q);
  const sx = from(fx, dx), sy = from(fy, dy), p = Math.round(Math.abs(dx ? fx - sx : fy - sy) * 15e4) / 1e4;   // the step's progress
  const x = p >= 8 ? sx + dx : sx, y = p >= 8 ? sy + dy : sy, n = (p >= 8 ? p - 7 : p + 8) - (mode === 1 ? 1 : 0);
  const rx = Math.round(fx), ry = Math.round(fy);
  const ok = (a, b) => a >= 0 && b >= 0 && a < N && b < N;
  if (!ok(x, y) || !ok(rx, ry)) return 0;
  const el = (a, b) => ok(a, b) ? (T.elev[b * N + a] || 0) : 0, fl = (a, b) => ok(a, b) ? T.flags[b * N + a] : 0;
  const ramp = f => f & 0x10000400, long = f => (f & 0x400) && (f & 0x800000);
  if (!ramp(fl(x, y)) && !ramp(fl(rx, ry))) return 0;
  const fix = (el(x, y) - el(rx, ry)) * 30;      // walkerSpot drew the rounded tile's elevation
  const f = fl(x, y), e = el(x, y), px = mode === 2 ? 1 : 2;
  if (!ramp(f)) return fix;
  if (long(f) && back && mode === 2) {            // a follower that turned: its run counted along the path it walked
    const L = followerRun(x, y, n, p >= 8 ? [[sx, sy], ...back] : back, nx, ny);
    return fix + (L.down == null ? 0 : L.down ? Math.max(0, 35 - Math.min(L.k, 29)) : Math.min(35, Math.min(L.k, 29)));
  }
  if (long(f)) {
    let r = 1;                                    // the pair's first or second tile: count the long-ramp run behind
    while (r < 16 && long(fl(x - r * dx, y - r * dy))) r++;
    const x1 = r % 2 ? x : x - dx, y1 = r % 2 ? y : y - dy, m = Math.min(r % 2 ? n : 15 + n, 29);
    const [ax, ay] = r % 2 && p >= 8 ? [nx, ny] : [dx, dy];   // the first tile's next step
    const e1 = el(x1, y1), ep = el(x1 - dx, y1 - dy), en = el(x1 + 2 * ax, y1 + 2 * ay);
    const down = e1 < ep ? true : e1 < en ? false : ep < e1 ? true : en < e1 ? false : null;
    return fix + (down == null ? 0 : down ? Math.max(0, 35 - px * m) : Math.min(35, px * m));
  }
  const m = Math.min(n, 14);
  if (e < el(x - dx, y - dy)) return fix + 30 - px * m;
  if (p >= 8 ? e < el(x + nx, y + ny) : e < el(x + dx, y + dy)) return fix + px * m;
  return fix;
}
// the exe's slope state at this point of the step, replayed from 6 tiles back (and back to the start of a long-ramp
// run: its pairs count from there; an older state has run out: timers are 15 / 30 counts): FUN_004D7580 on entering each tile with its previous tile and its next step (the route's;
// a roamer's: straight on), then figure_fine_step per count: while the timer runs (the count that ends it changes
// nothing) the offset moves 1 toward the target, 1 more on a ramp tile (0x10000400); timer 0: it drops 1. Entering a
// long ramp (0x400 + 0x800000) while the timer runs changes nothing; a tile without 0x10000400 zeroes the offset only.
function rampReplay(fx, fy, wd, mode, nd, back) {
  const [dx, dy] = DIR_STEP[wd & 7], sgn = Math.sign;
  const from = (q, c) => c > 0 ? Math.floor(q + 1e-6) : c < 0 ? Math.ceil(q - 1e-6) : Math.round(q);
  const sx = from(fx, dx), sy = from(fy, dy), p = Math.round(Math.abs(dx ? fx - sx : fy - sy) * 15e4) / 1e4;
  const ok = (a, b) => a >= 0 && b >= 0 && a < N && b < N;
  const el = (a, b) => ok(a, b) ? (T.elev[b * N + a] || 0) : 0, fl = (a, b) => ok(a, b) ? T.flags[b * N + a] : 0;
  const path = [];                                   // oldest first, ending with the current tile
  for (let k = 6; k >= 1; k--) path.push(back[k - 1] || [sx - k * dx, sy - k * dy]);
  path.push([sx, sy]);
  // a long-ramp run decides its pairs from where it starts: walk back to the tile before it (straight on past the
  // remembered tiles), the replay's zero state
  const isLong = t => { const f = fl(t[0], t[1]); return (f & 0x400) && (f & 0x800000); };
  for (let k = 0; k < 16 && isLong(path[0]); k++) {
    const [a, b] = path[0], [c, d] = path[1];
    path.unshift([a + sgn(a - c), b + sgn(b - d)]);
  }
  if (p >= 8) path.push([sx + dx, sy + dy]);
  const [cx, cy] = path[path.length - 1], rx = Math.round(fx), ry = Math.round(fy);
  const fix = (el(cx, cy) - el(rx, ry)) * 30;       // walkerSpot drew the rounded tile's elevation
  if (!path.some(t => fl(t[0], t[1]) & 0x10000400)) return fix;   // no ramp on the way: offset 0 (most walkers)
  const n = (p >= 8 ? p - 7 : p + 8) - (mode === 1 ? 1 : 0);   // fine steps since the current entry
  const st = { t: 0, o: 0, g: 0 };
  const dirTo = (a, b) => DIR_DELTA[`${sgn(b[0] - a[0])},${sgn(b[1] - a[1])}`];
  for (let j = 1; j < path.length; j++) {
    const [x, y] = path[j], [px, py] = path[j - 1], f = fl(x, y), e = el(x, y), ep = el(px, py);
    const last = j === path.length - 1;
    let d = mode === 1 ? dirTo(path[j - 1], path[j]) : last ? (p >= 8 ? nd : wd) : dirTo(path[j], path[j + 1]);
    const [ax, ay] = DIR_STEP[(d == null ? wd : d) & 7];
    if ((f & 0x400) && (f & 0x800000)) {
      if (!st.t) {
        const en = el(x + 2 * ax, y + 2 * ay);
        st.t = 30;
        if (e < ep || (!(e < en) && ep < e)) { st.g = 0; st.o = 35; }
        else if (e < en || en < e) { st.g = 35; st.o = 0; }
      }
    } else if (!(f & 0x10000400)) st.o = 0;
    else if (e < ep) { st.t = 15; st.g = 0; st.o = 30; }
    else if (e < el(x + ax, y + ay)) { st.t = 15; st.g = 30; st.o = 0; }
    else { st.t = 0; st.g = 0; st.o = 0; }
    const ramp = f & 0x10000400;
    for (let c = last ? n : 15; c > 0; c--) {
      if (!st.t) { if (st.o) st.o--; continue; }
      if (--st.t === 0) continue;
      for (let r = ramp ? 2 : 1; r > 0; r--) st.o += st.o < st.g ? 1 : st.o > st.g ? -1 : 0;
    }
  }
  return fix + st.o;
}
// the step origins a walker came through, newest first (for rampReplay): updated when its step origin changes
const pathMem = new Map();
function rampPath(id, x0, y0) {
  let m = pathMem.get(id);
  if (!m) pathMem.set(id, m = { s: [x0, y0], back: [] });
  else if (m.s[0] !== x0 || m.s[1] !== y0) { m.back.unshift(m.s); m.back.length = Math.min(m.back.length, 6); m.s = [x0, y0]; }
  return m.back;
}
function drawFollowers(out, WM, F, w, kk, fr) {
  const [id, x0, y0, , good] = w;
  const t = trailOf(id, x0, y0);
  const m = WM[(F.by_good && F.by_good[good]) || F.role];
  if (!m || !m.walk) return;
  for (let j = 1; j <= w[6]; j++) {
    const [fx, fy, dir, moving] = trailSpot(t, j, kk, id + ":" + j);
    const [depth, cx, cy] = figureSpot(fx, fy);
    const sp = sprite(m.walk.file || m.file, blockIndex(m.walk, dir, moving ? fr : 0));
    if (sp) { out.push([depth, fx, sp, cx - sp.ax, cy - sp.ay]); out[out.length - 1].wid = -1; }   // other figures (crops)
  }
}

// melee (sim crime.melee, docs/logic/services.md 6.1): frame field 7 = 0 or
// [kind "fight"|"die"|"work", t0, end, face dx, face dy, back dx, back dy, hits t0, foe role, mover].
// Frames come every 15 ticks, so the animation runs from these ticks, not from the frames.
// Returns [anim, x, y] while the walker stands fighting / dying at (x, y) at tick t, else null.
const LOOKS = new Set(["hidden", "shorn", "tree", "walk", "arrow"]);   // herding looks / a grower's tree kind / a wall sentry walking / an arrow (sim/export), not animations
// an animation look of the record itself still running at t (fightAnim's a0): kept to its end, not replaced by the
// next record's state because a step of the next record had begun (bugs.md 429: a monster's shot lost its last
// two frames, the next record's walk showed one tick before the shot's end); only while the next record has no step
// of its own (the same step record: a walker that set off is drawn walking)
function ownLook(w, n, t) {
  const a = w[7], same = !n || !n[8] || !w[8] || n[8][2] === w[8][2];
  return !!(a && !LOOKS.has(a[0]) && a[0] !== "die" && t < a[2] && same);
}
function fightAnim(w, n, t) {
  const a1 = n && n[7] && !LOOKS.has(n[7][0]) && n[7];
  if (a1 && a1[1] <= t) return [a1, n[1], n[2]];
  const a0 = w[7] && !LOOKS.has(w[7][0]) && w[7];
  if (a0 && (a0[0] === "die" || t < a0[2])) return [a0, w[1], w[2]];
  return null;
}

const TOWER_BACK = { 0: [0, 0], 2: [1, 0], 4: [1, 1], 6: [0, 1] };
const CRIMINALS = new Set(["disgruntled", "thief", "mugger", "vandal"]);
function drawFight(out, m, role, id, [a, x, y], t) {
  const [kind, t0, , fdx, fdy, bdx, bdy] = a;
  const dt = Math.max(0, Math.floor(t) - t0);
  if (fdx || fdy) lastDir[id] = DIR_DELTA[`${fdx},${fdy}`];
  let dir = lastDir[id] != null ? viewDir(lastDir[id]) : 3;   // world heading -> picture (view)
  // the two stand short of the tile centre, each on the side it came from (the exe's fine step stops at 6/15)
  // sentry on a tower / wall: slope_offset 98 / 18 (sim/military: [10] = [lift, ..]); a god's [10] is its sound kind
  // (sim gods.look), not a lift (bugs.md 265: a string here made the god's work look undrawn)
  const lift = (Array.isArray(a[10]) && a[10][0]) || 0;
  // tower sentry: the exe puts it on the tower's back tile of the current view every tick (0x004BB7B0: v0 (bx, by),
  // v2 (bx+1, by), v4 (bx+1, by+1), v6 (bx, by+1)); the sim keeps (bx, by), the view-0 spot
  const tb = lift === 98 ? TOWER_BACK[VIEW] : null;
  // a military melee ([11] = [tile progress at the start, heading], sim units.progress): figure_fight_tick 0x004D5F10
  // first steps a fighter whose progress is below 6 one fine unit a tick toward 6 (the closing-in); it stands at its
  // fine position: (p + 1) / 15 of a step on from its tile toward the heading for p < 8, (14 - p) / 15 back for 8..14
  // (the tile changes at 8; the walk table is one count ahead), the centre at 15. Others: 0.3 back (crime melee)
  let ox = 0.3 * bdx, oy = 0.3 * bdy;
  // a monster's missile attack (28, look "work"/"special", sim monsters.look): it stands where its step was ([11])
  if ((kind === "fight" || (kind === "work" && a[8] === "special")) && Array.isArray(a[11])) {
    const [p0, hx, hy] = a[11], p = p0 < 6 ? Math.min(6, p0 + dt) : p0;
    const k = p >= 15 ? 0 : p < 8 ? (p + 1) / 15 : -(14 - p) / 15;
    ox = hx * k; oy = hy * k;
  }
  const fx = x + ox + (tb ? tb[0] : 0), fy = y + oy + (tb ? tb[1] : 0);
  // the road term (figureSpot) standing: the tile it walked in from (its walk's memory) against its own; not a statue (0x46)
  const rise = ROAD_RISE.test(role) && typeof id === "number" ? roadRise(id, x, y, x, y, 0, false) : 10;
  const [depth, cx, cy0] = figureSpot(fx, fy, { lifted: !!lift }, rise);      // +0x1D: drawn at row + 2 (draw-order.md 3.7)
  // a god's work look ([11] = its tile progress at the look's start, sim gods.look): walker_draw adds the walk table
  // 0x005F0658 / 0x005F06D8 [view dir][progress] to a standing figure too; progress 15 (after figure_walk_then: bolts,
  // curse) is the centre, progress 0 (a blessing from the visit's roam step) is 1/15 of a step on (bugs.md 262)
  const p0 = role === "god" && a[11] === 0 ? WALK_P0[dir] : null;
  const cy = cy0 - lift + (p0 ? p0[1] : 0);
  const cxp = cx + (p0 ? p0[0] : 0);
  let blk, fr;
  if (kind === "die") {                                                     // timer/2 (wolf, hoplite: timer), then the corpse
    blk = m.die;                                                            // monsters / heroes: their whole death (bug 386)
    // min(timer (/2), n - 1), n = FUN_005AF5F0(die group) = its anim_frames (bug 393: was capped at 7 for all but
    // monsters / heroes, so the 15-frame deaths of Persian / Amazon / Centaur invaders stopped half way)
    fr = Math.min(blk ? (blk.frames || 8) - 1 : 7, m.die_rate === 1 ? dt : dt >> 1);
    if (blk && blk.dir0) dir = 0;                                           // Ares' warriors: FUN_005af770(die, f, 0)
  }
  else if (kind === "carcass") { blk = m.die; fr = Math.min(7, dt); }       // shot prey (figure_boar action 10): 1 per tick
  else if (kind === "work" && a[8] && m.work && m.work[a[8]]) {          // herder: shear / milk / guard
    blk = m.work[a[8]];                                                    // one frame per tick (figure_shepherd)
    if (blk.chain) {                                                       // urchin collector: action 7, 8 x5, 9 (play_diver.py)
      // `cycles` loops of the chain, then `last` (the timer passed 408: action 9 to its end, held on its last frame)
      const len = ch => ch.reduce((u, c) => u + c.frames * (c.repeat || 1), 0), C = len(blk.chain);
      const fin = blk.last && blk.cycles != null && dt >= blk.cycles * C;
      const ch = fin ? blk.last : blk.chain;
      let r = fin ? Math.min(dt - blk.cycles * C, len(blk.last) - 1) : dt % C;
      for (const c of ch) {
        const n = c.frames * (c.repeat || 1);
        if (r < n) { blk = { ...blk, start: c.start, frames: c.frames }; fr = r % c.frames; break; }
        r -= n;
      }
    } else if (blk.seq) {                                                  // tower sentry idle: frames held seq[i] ticks
      const tot = blk.seq.reduce((u, v) => u + v, 0);
      let r = dt % tot; fr = 0;
      while (r >= blk.seq[fr]) r -= blk.seq[fr++];
    } else if (blk.rate === 100) fr = imageStep(blk.speed, t);              // invaders at a wall (siege, direction 0xB)
    else if (blk.clamp != null) fr = Math.min(blk.clamp, (blk.offset || 0) + Math.floor(dt / (blk.ticks_per_frame || 1)));   // wall sentry shot; Amazons' throw (attack_timer from 1)
    // the rabble's throw (fig_handler_rabble 0x004B31F0, rate 100 on anim_frame): its counter c0 (a[12]: the frame
    // its walk left it on, sim forces acount; 0 after a stone), stepped in the look's first tick, +1 every
    // ticks_per_frame (bug 436)
    else if (blk.counter) fr = ((a[12] == null || !m.walk ? 0 : a[12] % (m.walk.frames || 1)) + (blk.offset || 0) + Math.floor(dt / (blk.ticks_per_frame || 1))) % (blk.frames || 1);
    // artisan: 6 frames x 2 ticks; a monster's shot (28): offset 1, the exe draws frame 1 at the entry tick (on-enter
    // 0x00530EA0 sets 0, the tail 0x004C8D4B steps it in the same call) .. n - 1 at entry + n - 2 (bugs.md 429)
    else fr = ((blk.offset || 0) + Math.floor(dt / (blk.ticks_per_frame || 1))) % (blk.loop || blk.frames || 1);
  } else {
    blk = m.fight || (m.work && Object.values(m.work)[0]);                // hunter/woodcutter: no fight art (guess)
    const rule = m.fight_rule, k = dt % 24;
    const c0 = a[12] == null || !m.walk ? 0 : a[12] % (m.walk.frames || 1);                               // fight rules: docs/logic/military.md
    if (m.frame_rule === "tick") fr = dt % ((blk && blk.frames) || 1);    // monster / hero: +1 a tick, all frames (bug 386)
    else if (rule === "hoplite") { fr = k < ((blk && blk.frames) || 8) ? k : 0; dir = 0; }   // attack_timer < n (8; Ares' warriors 20), direction 0 (exe bug, kept)
    else if (rule === "amazon") fr = k < 12 ? k : 0;                    // Artemis' Amazons (0x004B31F0): attack_timer < 12
    else if (rule === "enemy") fr = k < 12 ? 0 : (k - 10) >> 1;           // infantry / cavalry: (attack_timer - 10)/2
    // enemy archer (fig_handler_enemy_archer 0x004B99B0 action 5): sprite_anim_step(fight group, rate 100) on its
    // anim_frame: +1 every ticks_per_frame from its counter's origin (a[7], sim invaders.fight_started: the fight's
    // start, or the shot it was in when attacked; bug 393)
    // a[12] (sim units.counter_ref): figure_fight_start resets the mover's anim_frame only; the other fights on from
    // its walk counter (the walk frame of tick a[12], as walkers are drawn; null = 0)
    else if (rule === "rate100") fr = c0 + Math.floor(Math.max(0, Math.floor(t) - (a[7] || t0)) / (blk.ticks_per_frame || 1));
    // rabble (fig_handler_rabble 0x004B31F0): the prologue's +1 a tick and sprite_anim_step(6945, rate 100)'s +1 on
    // the gated ticks (bug 393; before: +1 a tick)
    else if (rule === "rabble") fr = c0 + dt + Math.floor(dt / (blk.ticks_per_frame || 1));
    else if (rule === "tick") fr = (c0 + dt) % ((blk && blk.frames) || 8);   // wolf: +1 per tick
    else if (!CRIMINALS.has(role)) {
      const k = dt % 24;                                                  // watchman: stance 12 ticks, swing 12
      fr = k < 12 ? 0 : (k - 12) >> 1;
    } else fr = dt % 8;                                                   // criminals: 8 frames, 1 per tick
  }
  if (!blk) { blk = m.walk; fr = 0; }
  const sp = blk && sprite(blk.file || m.file, blockIndex(blk, dir, fr));
  if (sp) out.push([depth, fx, sp, cxp - sp.ax, cy - sp.ay]);
  // a figure standing in a look (fighting, working, a god appearing / blessing / casting) is right-clickable too
  // (bugs.md 325: a god's window); its tile is the one it stands on
  if (sp && typeof id === "number")
    WALKER_HITS.push([id, cxp - sp.ax, cy - sp.ay, sp.w, sp.h, depth, Math.round(x), Math.round(y), blk.file || m.file, blockIndex(blk, dir, fr)]);
  if (m.layers) shipLayers(out, m, id, kind === "work" ? a[8] : kind, dir, dt, depth, fx, cx, cy, false);
}
// sprite_anim_step 0x005AF8C0 with rate 100 (bug 393): the frame steps on a tick only if the wall-clock gate
// 0x006668EC[speed] is set that game turn (0x00413330: once per 20 * speed ms; speed = the group's first image +0x3A).
// The exe runs one tick per game turn (simulation_due 0x005168A0), so the frame steps every tick while a tick lasts at
// least 20 * speed ms, else about once per 20 * speed ms. Counted from the game tick, not the look's start: the
// figure's counter (+0x01) runs on across the hits (ours re-sends the siege look at each hit, every 4 ticks).
// Not modelled: a gate that fires in a game turn without a tick (the exe's turns outnumber its ticks) is lost.
function imageStep(speed, t) {
  const msTick = 1000 / Math.max(1, P.rate || 1);
  return Math.floor(Math.floor(t) * Math.min(1, msTick / (20 * (speed || 0))));
}
// the walk table's progress-0 row (0x005F0658 x / 0x005F06D8 y, by view direction; docs/play/walkers.md "Position")
const WALK_P0 = [[2, -1], [4, 0], [2, 1], [0, 2], [-2, 1], [-4, 0], [-2, -1], [0, -2]];

// a trireme's crew and selection-flag overlays (data/play/military.json roles.trireme layers / flag; navy.md
// "Pictures"), the crew frame by its own ticks_per_frame. walker_draw 0x0044FEF0 (type 0x39): the crew (+0x150) at
// the hull's point + (-2 + 1, -10), the flag (+0x180) at + (-2 + 1 + F+0x6C, -10 + 14 + F+0x6D) (0 for a trireme).
// Crew seen whole at the hull's point + (-1, -10) (oracle trireme-overlays, tick 28: PoseidonImps 8309, every
// non-shadow pixel); the diamond patch in 1B-trireme t_83.bmp is the exe's stale screen memory (navy.md "Pictures")
function shipLayers(out, m, id, key, dir, dt, depth, fx, cx, cy, moving) {
  for (const L of m.layers[key] || []) {
    const sp = sprite(L.file, blockIndex(L, dir, Math.floor(dt / (L.ticks_per_frame || 1))));
    if (sp) out.push([depth, fx, sp, cx - 1 - sp.ax, cy - 10 - sp.ay]);
  }
  const F = m.flag && window.MilPanel && MilPanel.ships.includes(id) && (moving ? m.flag.walk : m.flag.still);
  const fs = F && sprite(F.file, blockIndex(F, dir, dt));
  if (fs) out.push([depth, fx, fs, cx - 1 - fs.ax, cy + 4 - fs.ay]);
}

// arrow (sim/military defences.look): ["arrow", t0, end, .., role, false, [src x, y, aim x, y, height, army]].
// The exe's line move: 4 fine units a tick (15 a tile); walker_draw 0x0044FEF0's line branch: the figure point (+2,
// +10) - line_counter (10 at the start, 0x004D9D70; -1 a fine unit, figure_line_move 0x004D9750) - slope_offset, a
// tower arrow's offset falling 3 a tick (walker_player_missile 0x004BACE0); the shadow (types 0x2D / 0x34: the extra
// picture) first, at the arrow's top-left + (0, 10). Picture SprAmbient group 79 (enemy: army 0 -> 51, 1 -> 71),
// 32 directions; the index from the screen angle (ours: image 30 points up, 6 right, clockwise; seen).
function drawArrow(out, a, t) {
  const A = MAP.military && MAP.military.arrow;
  if (!A) return;
  const [sx, sy, ax, ay, h0, army, d32, grp] = a[10];
  const dt = Math.max(0, t - a[1]), L = Math.max(1, Math.abs(ax - sx), Math.abs(ay - sy));
  const u = dt * 4 / 15 / L;
  if (u > 1) return;
  const fx = sx + (ax - sx) * u, fy = sy + (ay - sy) * u;
  const ex = tileX(ax, ay) - tileX(sx, sy), ey = tileY(ax, ay) - tileY(sx, sy);
  let i = (30 + Math.round(Math.atan2(ex, -ey) / (Math.PI / 16)) + 64) & 31;      // older recordings (no dir32)
  // a god's bolt (sim/gods bolts.look) / a monster's missile (sim/heroes monsters.shoot; data/play/heroes.json
  // "missile": group 0x222F for every monster, the handlers read the missile's own zeroed +0x0B): 8 directions,
  // sprite_anim_step(.., rate 100) on the missile's counter from 0: a frame every ticks_per_frame ticks. Direction:
  // ((dir32 - 4 view) & 31) >> 2, dir32 = FUN_0058D050(from, to) << 1 (+0x11, sim defences.dir16; oracle 1I-missile
  // tick 1694: dir32 30 -> image 1212 + 3*8 + 7; 1H-bolt: god bolts dir32 30 / 24 -> directions 7 / 6)
  if (a[8] === "god_bolt" || a[8] === "monster_missile") {
    const di = d32 != null ? ((d32 - 4 * VIEW) & 31) >> 2 : i >> 2;
    const GB = a[8] === "god_bolt" ? window.Gods && Gods.bolt(army) : MAP.heroesMissile, [depth, cx, cy] = figureSpot(fx, fy);
    const fr = Math.floor(Math.floor(dt) / ((GB && GB.ticks_per_frame) || 1)) % ((GB && GB.frames) || 1);
    const sp = GB && sprite(GB.file, GB.start + fr * GB.dirs + di);
    if (sp) out.push([depth, fx, sp, cx - sp.ax, cy - Math.max(0, 10 - 4 * dt) - sp.ay]);
    return;
  }
  // the picture group by the shooter (sim defences.arrow_group, oracle 1D-arrows): a79 = SprAmbient 79 / shadow 78,
  // a71 = 71 / 70 (32 directions each), a51 = 51 / 50 (one picture); frames without it (older recordings) as before
  const EA = MAP.military.enemy_arrows;
  const E = grp ? null : a[8] === "enemy_arrow" && EA[String(army)];
  const B = grp === "a71" ? EA["1"] : grp === "a51" ? EA["0"] : grp === "a79" ? A : (E || A);
  if (grp && d32 != null) i = ((((d32 - 4 * VIEW) & 31) - 13) & 31);   // walker_player_missile 0x004BACE0 /
                                                                          // fig_handler_enemy_missile 0x004BD970
  const h = h0 > 100 ? Math.max(0, h0 - 3 * dt) : h0;                    // a tower arrow falls 3 px a tick (floor 0: ours)
  const [depth, cx, cy] = figureSpot(fx, fy), lc = Math.max(0, 10 - 4 * dt);
  const sh = sprite(B.file, B.shadow + (B.dirs > 1 ? i : 0)), sp = sprite(B.file, B.start + (B.dirs > 1 ? i : 0));
  if (!sp) return;
  const qx = cx - sp.ax, qy = cy - lc - h - sp.ay;
  if (sh) out.push([depth, fx, sh, qx, qy + 10]);
  out.push([depth, fx, sp, qx, qy]);                                             // after its shadow (push order)
}

// a cart waiting with nowhere to go (frame `waiting`, Figure+0x7B) under See Husbandry / Industry / problems: walker_draw
// 0x0044FEF0 calls the overlay's +0x04 (0x00564B00) when +0x14 holds (types 4/9/36 with +0x7B; 0x0055FFA0, 0x00564AC0):
// SPR_PROBLEM_ICONS + 11 (the '?') with its top-left at the walker_draw point of the figure's tile: the tile's box
// top-left (tileX, tileY - 30 elev), as measured on the oracle (re/oracle/runs/cartwait2/p1.bmp, working city under See
// problems: 3 of 3 icons exactly at their carts' tile points)
function cartWaitIcon(out, id, depth, fx, fy) {
  const sp = window.Overlays && P.f0 && P.f0.waiting && P.f0.waiting.includes(id) && Overlays.cartIcon();
  const x = Math.round(fx), y = Math.round(fy);
  if (sp) out.push([depth, fx, sp, tileX(x, y), tileY(x, y) - (T.elev[y * N + x] || 0) * 30]);
}

const departing = new Map();                         // id -> its last step into a building (sceneWalkers)
const shownState = new Map();                        // id -> [role, good, amount, followers, look] being drawn
// this frame's walker pictures [id, left, top, w, h, depth, tile x, tile y, file, index] (right click, ui.js)
let WALKER_HITS = [];
// per walker id: [left, top, tile x, tile y] of its body picture (the exe's crop anchor 0x007D3B3C/38, walker_draw
// 0x0044FEF0: the figure's main sprite's top-left); every draw entry of a figure carries .wid = its id, the
// pictures of other figures drawn with it (ox pairs, trailer, assistants) -1 (walker-window crops, play.js)
let ANCHORS = new Map();
function sceneWalkers(out) {
  const WM = MAP.walkers && MAP.walkers.roles;
  WALKER_HITS = []; ANCHORS = new Map();
  if (!P.f0 || !WM) return;
  for (const id of Object.keys(trails)) if (!trailSeen.has(+id)) delete trails[id];
  if (shownState.size > 4 * (P.f0 ? P.f0.walkers.length : 0) + 100) shownState.clear();
  trailSeen = new Set();
  const f0 = P.f0, f1 = P.f1 && P.f1.tick > f0.tick ? P.f1 : null;
  const k = f1 ? Math.min(1, Math.max(0, (P.t - f0.tick) / (f1.tick - f0.tick))) : 0;
  const next = new Map(f1 ? f1.walkers.map(w => [w[0], w]) : []);
  // walkers that went into a building before f1: their last step, toward the tile they went in from
  const gone = new Map(f1 && f1.gone ? f1.gone.map(g => [g[0], g]) : []);
  const tick = Math.floor(P.t);
  // walkers no longer in f0 still finishing their step into a building (see below)
  const inF0 = new Set(f0.walkers.map(w => w[0]));
  const synth = [];
  for (const [id, d] of departing) {
    if (P.t >= d.st[3] || P.t < d.st[2] - 120) { departing.delete(id); continue; }
    if (!inF0.has(id)) synth.push(Object.assign(d.rec.slice(), { 1: d.X, 2: d.Y, 8: d.st }));
  }
  // draw colours (+0x168, sim heroes.frame "tint": a devoured victim red 0x7C00): every picture of that walker
  const tints = new Map([...(f0.tint || []), ...((f1 && f1.tint) || [])]);
  for (const w0 of f0.walkers.concat(synth)) { const o0 = out.length; try {
    // what a walker carries / looks like changes when its step ends, not when it starts: the sim sets it on
    // arrival, and the step to that tile is drawn over the following ticks (bugs.md 116). So the state
    // drawn is the last one whose record's step had finished; the position still comes from the newest
    // (a new state is first seen with the step it arrived by: it is held until that step's end)
    const n0 = next.get(w0[0]), rec = n0 && n0[8] && n0[8][2] <= P.t ? n0 : w0;
    const now = [rec[3], rec[4], rec[5], rec[6], rec[7]], key = JSON.stringify(now);
    let ss = shownState.get(w0[0]);
    if (!ss) shownState.set(w0[0], ss = { cur: now, key, pend: null, pkey: key, at: 0 });
    else if (key !== ss.key && key !== ss.pkey) { ss.pend = now; ss.pkey = key; ss.at = rec[8] ? rec[8][3] : P.t; }
    if (ss.pend && P.t >= ss.at) { ss.cur = ss.pend; ss.key = ss.pkey; ss.pend = null; }
    const shown = ss.cur;
    const w = Object.assign(w0.slice(), { 3: shown[0], 4: shown[1], 5: shown[2], 6: shown[3],
                                          7: (rec[7] && !LOOKS.has(rec[7][0])) || ownLook(w0, n0, P.t) ? w0[7] : shown[4] });
    const [id, , , role, good, amount] = w;
    if (window.Overlays && Overlays.walkerHidden(role, id)) continue;
    if (w[7] && w[7][0] === "arrow") { drawArrow(out, w[7], P.t); continue; }   // sentries' / archers' arrows
    let m = roleOf(WM, role, good);
    if (!m) continue;
    const look = w[7] && w[7][0];
    if (look === "hidden") continue;                 // shorn / milked animal, herder still in the farm
    if (look === "shorn" && m.shorn) m = Object.assign({ file: m.shorn.file || m.file }, m.shorn);
    if (look === "tree" && m.trees && m.trees[w[7][8]]) m = Object.assign({}, m, m.trees[w[7][8]]);   // orange grower
    const n = next.get(id);
    const fa = fightAnim(w, n, P.t);
    if (fa) { drawFight(out, m, role, id, fa, P.t); continue; }
    // the walker's own step (w[8] = [from x, from y, start tick, end tick], sim/live.py record_frame), from
    // the newest record whose step has begun: smooth at any frame interval. Without one (boats, some
    // animals), the frame-to-frame move as before.
    const src = n && n[8] && n[8][2] <= P.t ? n : w;
    let st = src[8] && src[8][2] <= P.t ? src[8] : null, X = src[1], Y = src[2];
    // went into a building: once the step to its door has been drawn, one more step onto the building's
    // tile (sim/live.py went_into), where the building hides it, as the exe's figures walk in (bugs.md
    // 114: the gone tile was the door, so the walker stood there a step, then vanished)
    const gw = !n && gone.get(id);
    if (gw && gw.length >= 5 && (!st || P.t >= st[3])) {
      const t0 = st ? st[3] : f0.tick, d = st ? st[3] - st[2] : 15;
      st = [X, Y, t0, t0 + d]; X = gw[3]; Y = gw[4];
      departing.set(id, { rec: w, st, X, Y });
    }
    let x0, y0, x1, y1, kk;
    if (st) { x0 = st[0]; y0 = st[1]; x1 = X; y1 = Y; kk = Math.min(1, Math.max(0, (P.t - st[2]) / (st[3] - st[2]))); }
    else {
      x0 = w[1]; y0 = w[2]; x1 = n ? n[1] : x0; y1 = n ? n[2] : y0; kk = k;
      // the next frame's step starts later, from the tile it stands on now: it stands until then (soldiers and
      // invaders change tile at progress 8, several ticks after their route starts; bugs.md 432)
      if (n && n[8] && n[8][2] > P.t && n[8][0] === x0 && n[8][1] === y0) { x1 = x0; y1 = y0; }
    }
    const dx = Math.sign(x1 - x0), dy = Math.sign(y1 - y0);
    if (dx || dy) lastDir[id] = DIR_DELTA[`${dx},${dy}`];
    const dir = lastDir[id] != null ? viewDir(lastDir[id]) : 3;   // world heading -> picture (view)
    const moving = !!(dx || dy) && kk < 1;
    // monsters / heroes / gods: frame +1 every tick, walking or standing, over the group's own count (figure_hero_update
    // 0x004C9D18, monster_anim_info 0x00533B60; bug 386: was tick % 12 and still when standing, half of a 23-frame walk;
    // gods: figure_god_handler 0x004C5D40's walk-group actions, sprite_anim_step rate 0, bug 393)
    // invaders standing outside a look are in action 7 (hold: the walk group's frame 0) or lost (-> 7): frame 0
    // others: +1 a tick while moving, wrapped at the drawn group's own count (blockIndex: fr % frames; the
    // anim_frames of the group's first image, e.g. 12 for SprMain walkers, 15 / 17 / 18 / 11 for Persian, Amazon,
    // Centaur, Ares warrior invaders, 17..28 for gods; sprite_anim_step 0x005AF8C0 wraps at +0x1E; bug 393: was
    // tick % 12 for every group, so 15-frame walks never showed frames 12..14)
    const fr = m.frame_rule === "tick" ? tick % ((m.walk && m.walk.frames) || 1)
      : moving ? (m.anim ? Math.floor((tick % 12) / 3) : tick) : 0;
    const fx = x0 + (x1 - x0) * kk, fy = y0 + (y1 - y0) * kk;
    const wlift = (look === "walk" && w[7][10] && w[7][10][0]) || 0;     // a wall sentry on the wall (sim/military)
    const rise = ROAD_RISE.test(role) ? roadRise(id, x0, y0, x1, y1, kk, moving) : 10;
    const [depth, cx, cy1] = figureSpot(fx, fy, { lifted: !!wlift, water: BOATS.has(role), big: BIG.has(role) }, rise);
    const nd = st && st.length >= 7 ? DIR_DELTA[`${Math.sign(st[5] - X)},${Math.sign(st[6] - Y)}`] : undefined;
    const back = BOATS.has(role) ? null : rampPath(id, x0, y0);
    const cy = cy1 - wlift - (moving && !BOATS.has(role) ? rampLift(fx, fy, lastDir[id], st && st[4] ? 1 : 0, nd, back) : 0);
    const put = (file, idx, ox = 0, oy = 0, d = depth, body = false) => {
      const sp = sprite(file, idx);
      if (!sp) return;
      out.push([d, fx, sp, cx + ox - sp.ax, cy + oy - sp.ay]);
      if (body || !ANCHORS.has(id)) ANCHORS.set(id, [cx + ox - sp.ax, cy + oy - sp.ay, Math.round(fx), Math.round(fy)]);
      WALKER_HITS.push([id, cx + ox - sp.ax, cy + oy - sp.ay, sp.w, sp.h, d, Math.round(fx), Math.round(fy), file, idx]);
    };
    if (w[6] > 0 && m.followers) { trailSeen.add(id); drawFollowers(out, WM, m.followers, Object.assign(w.slice(), { 1: x1, 2: y1 }), kk, fr); }
    if (m.variants) m = Object.assign({ file: m.file }, m.variants[id % m.variants.length]);
    let walk = m.walk, file = m.file;
    const c = m.carry && good && m.carry[good];
    if (m.by_good && m.by_good[good]) { walk = m.by_good[good].walk || walk; file = m.by_good[good].file || file; }
    if (c && c.overlay) {                        // cart: pusher + cart overlay, cart over the pusher only facing S
      const o = c.overlay, lvl = Math.min(o.levels - 1, (amount || 0) <= 200 ? 0 : (amount || 0) <= 400 ? 1 : 2);
      // the cargo: walker_draw's extra picture, from the plain point (the pusher's - (2, 10)) + the light table
      const cart = () => put(o.file, o.start + lvl * 8 + dir, o.offsets[dir][0] - 2, o.offsets[dir][1] - 10);
      if (dir !== 3) cart();
      put(file, blockIndex(walk, dir, fr), 0, 0, depth, true);   // the pusher is the figure's own picture
      if (dir === 3) cart();
      cartWaitIcon(out, id, depth, fx, fy);
      continue;
    }
    if (c && c.heavy) {
      // ox train (bugs.md 105, 111, 113): in the exe these are separate figures following the one ahead
      // (cart_spawn_helpers 0x004ADF30): the cart figure (the driver) in front, then 1-4 ox pairs
      // (FIG_OXCART 28, action 6, packed 0x6605 = SprMain group_4 walk; driver 0x6613 = group_18), then the trailer (FIG_OXCART, action 7, the
      // cargo picture); oxen: loads - 1 clamped to 0..3, + 1 (marble with >= 4 loads: 1). The follow
      // (0x004D7340) keeps a follower's tile progress at its leader's minus 12 (oxen) or 13 (the trailer)
      // fifteenths of a tile, along the leader's path, facing the way it goes; the trailer is drawn as the
      // figure's extra picture, offset (0, +17) from the plain position where a walker is at (+2, +10)
      // (figure_oxcart 0x004C3680 sets fields 0x6C/0x6D; walker_draw 0x0044FEF0). Each part sorts by its own spot.
      const loads = Math.max(1, Math.ceil((amount || 0) / 100));
      const nOx = good === "marble" && loads >= 4 ? 1 : Math.min(4, loads);
      const tr = trailOf(id, x1, y1), t = c.trailer;
      // past the trail seen: straight back, from its last two points or against the driver's heading (bugs.md 387:
      // a standing cart showed ox and trailer piled on its own tile, "a cart and a loose block")
      const ld = tr.length >= 2 ? [Math.sign(tr[tr.length - 1][0] - tr[tr.length - 2][0]), Math.sign(tr[tr.length - 1][1] - tr[tr.length - 2][1])]
        : lastDir[id] != null ? DIR_STEP[lastDir[id] & 7].map(v => -v) : null;
      const lvl = Math.min((t.levels || 1) - 1, loads <= 2 ? 0 : loads <= 4 ? 1 : 2);   // FUN_004AD760
      put(c.walker.file, blockIndex(c.walker.walk, dir, fr));
      cartWaitIcon(out, id, depth, fx, fy);
      let u = 0;
      for (let j = 1; j <= nOx + 1; j++) {
        const trailer = j > nOx;
        u += trailer ? 13 / 15 : 12 / 15;
        const [px, py, pd, mv] = trailSpot(tr, u, kk, id + ":" + j, ld);
        const tb = trailBack(tr, u, kk);              // the leader's tiles behind this one's step: its own way here
        const [d, qx, qy0] = figureSpot(px, py), qy = qy0 - (mv ? rampLift(px, py, lastDir[id + ":" + j], 2, undefined, tb) : 0);   // FUN_004D7340: 1 px a step
        const sl = !trailer && c.ox.slopes ? oxSlope(px, py, lastDir[id + ":" + j], tb) : 0;   // ramps: group_5 up / group_6 down
        const ow = sl ? Object.assign({}, c.ox.walk, { start: sl > 0 ? c.ox.slopes.up : c.ox.slopes.down }) : c.ox.walk;
        const sp = trailer ? sprite(t.file, t.start + lvl * 8 + pd) : sprite(c.ox.file, blockIndex(ow, pd, mv ? fr : 0));
        if (!sp) continue;
        const ox = trailer ? -2 : 0, oy = trailer ? 7 : 0;
        out.push([d, px, sp, qx + ox - sp.ax, qy + oy - sp.ay]);
        out[out.length - 1].wid = -1;                // ox pairs and trailer: figures of their own in the exe
        WALKER_HITS.push([id, qx + ox - sp.ax, qy + oy - sp.ay, sp.w, sp.h, d, Math.round(px), Math.round(py), c.walker.file, blockIndex(c.walker.walk, dir, 0)]);
      }
      continue;
    }
    if (c && c.walk) { walk = c.walk; file = c.file || file; }
    else if (c && c.start != null) { walk = c; file = c.file || file; }
    if (!walk) continue;
    // a hero on deep water outside a bridge (figure_hero_update 0x004C8F50, bug 392): his g4 group (action 0x13
    // look, frame +1 a tick over its own count) and the raft as his extra picture (SprAmbient rank 87, first +
    // frame * 16 + 2 * view dir, 4 frames), from the plain point, under him except facing S (walker_draw)
    const rf = role === "hero" && m.special && window.Heroes && Heroes.swimming(Math.round(fx), Math.round(fy)) ? Heroes.raft() : null;
    if (rf) {
      const raftPic = () => put(rf.file, rf.first + rf.stride * (Math.floor(performance.now() / rf.ms) % rf.frames) + 2 * dir, rf.dx, rf.dy);
      if (dir !== 3) raftPic();
      put(m.special.file || file, blockIndex(m.special, dir, tick % (m.special.frames || 1)), 0, 0, depth, true);
      if (dir === 3) raftPic();
      continue;
    }
    put(walk.file || file, blockIndex(walk, dir, fr));
    if (m.layers) shipLayers(out, m, id, moving ? "walk" : "idle", dir, moving ? fr : 0, depth, fx, cx, cy, moving);
  } catch (e) { sceneError(e, "walker " + w0[3]); } finally {
    const tc = tints.get(w0[0]);
    if (tc) for (let i = o0; i < out.length; i++) out[i].tint = tc;
    for (let i = o0; i < out.length; i++) if (out[i].wid == null) out[i].wid = w0[0];
    if (!ANCHORS.has(w0[0])) for (let i = o0; i < out.length; i++) if (out[i].wid === w0[0]) {   // fights: the first own picture
      ANCHORS.set(w0[0], [out[i][3], out[i][4], Math.round(w0[1]), Math.round(w0[2])]); break;
    }
  } }
  const o1 = out.length;
  if (window.Heroes) Heroes.statues(out);          // petrified figures (0x46), grey (heroes.js)
  for (let i = o1; i < out.length; i++) out[i].wid = -1;
}

// --- walls: flag 0x4000 tiles, pictures as the exe's wall pass 0x0049FD70 (docs/play/rotation.md "Walls"):
// neighbours N, NE, E, SE, S, SW, W, NW (world) count as wall when they carry 0x4000 or 0x8000 (tower and
// gatehouse tiles, 0x0049F6F0); the first record of pattern table 0x00636820 that fits (1: no wall there, 0:
// wall, 2: any) gives the picture offset of column view/2; a tower beside the tile (0x0049F7D0, per view)
// adjusts it (0x0049F8A0), and views 2 and 6 swap mirror pairs (0x0049F560) of pictures drawn mirrored there.
// Oracle re/oracle/scenarios/rotation-walls.txt + tools/oracle_walls.py: 40/40 wall tiles in each of the 4 views.
let wallCache = { T: null, tiles: [] };
const onTower = (x, y) => { const b = buildingAt(x, y); return !!b && (b.key === "tower" || b.key === "gatehouse"); };
const WALL_T = [   // exe 0x00636820: [pattern N..NW as 8 digits, offsets for views 0, 2, 4, 6]
  ["12121212", 26, 26, 26, 26], ["12121202", 15, 10, 5, 16], ["02121212", 16, 15, 10, 5], ["12021212", 5, 16, 15, 10],
  ["12120212", 10, 5, 16, 15], ["12021202", 1, 4, 1, 4], ["02120212", 4, 1, 4, 1], ["12120002", 10, 7, 5, 12],
  ["02121200", 12, 10, 7, 5], ["00021212", 5, 12, 10, 7], ["12000212", 7, 5, 12, 10], ["12120102", 10, 22, 5, 12],
  ["02121201", 12, 10, 22, 5], ["01021212", 5, 12, 10, 22], ["12010212", 22, 5, 12, 10], ["12000002", 3, 2, 1, 4],
  ["02120000", 4, 3, 2, 1], ["00021200", 1, 4, 3, 2], ["00000212", 2, 1, 4, 3], ["12010002", 22, 24, 1, 4],
  ["02120100", 4, 22, 24, 1], ["00021201", 1, 4, 22, 24], ["01000212", 24, 1, 4, 22], ["12000102", 25, 22, 1, 4],
  ["02120001", 4, 25, 22, 1], ["01021200", 1, 4, 25, 22], ["00010212", 22, 1, 4, 25], ["12010102", 22, 22, 1, 4],
  ["02120101", 4, 22, 22, 1], ["01021201", 1, 4, 22, 22], ["01010212", 22, 1, 4, 22], ["01010101", 22, 22, 22, 22],
  ["01010100", 22, 22, 23, 22], ["00010101", 22, 22, 22, 23], ["01000101", 23, 22, 22, 22], ["01010001", 22, 23, 22, 22],
  ["01000100", 17, 18, 17, 18], ["00010001", 18, 17, 18, 17], ["01010000", 22, 21, 19, 22], ["00010100", 22, 22, 21, 19],
  ["00000101", 19, 22, 22, 21], ["01000001", 21, 19, 22, 22], ["01000000", 21, 20, 19, 22], ["00010000", 22, 21, 20, 19],
  ["00000100", 19, 22, 21, 20], ["00000001", 20, 19, 22, 21], ["00000000", 0, 0, 0, 0]];
const WALL_NB = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];
// 0x0049F7D0: the tower neighbour per view, [side giving 2, side giving 1]
const WALL_TOWER = { 0: [[0, -1], [-1, 0]], 2: [[1, 0], [0, -1]], 4: [[0, 1], [1, 0]], 6: [[-1, 0], [0, 1]] };
// 0x0049F560 (views 2 and 6)
const WALL_SWAP = [0, 4, 3, 2, 1, 10, 6, 7, 9, 8, 5, 11, 12, 14, 13, 16, 15, 17, 18, 21, 20, 19, 22, 23, 25, 24, 26, 28, 27,
  30, 29, 32, 31, 33, 35, 34];
function wallTowerAdjust(k, t) {   // 0x0049F8A0
  switch (k) {
    case 0: case 20: return t ? 33 : k;
    case 1: return t === 1 ? 32 : 1;
    case 2: case 9: case 19: return t === 2 ? 29 : k;
    case 3: case 8: case 21: return t === 1 ? 30 : k;
    case 4: return t === 2 ? 31 : 4;
    case 22: return t === 2 ? 34 : t === 1 ? 35 : 22;
  }
  return k;
}
function wallImage(x, y) {
  const has = (xx, yy) => xx >= 0 && yy >= 0 && xx < N && yy < N && (!!(T.flags[yy * N + xx] & 0x4000) || onTower(xx, yy));
  const free = WALL_NB.map(([dx, dy]) => !has(x + dx, y + dy));
  const rec = WALL_T.find(r => [...r[0]].every((p, i) => p === "2" || (p === "1") === free[i]));
  let k = rec ? rec[1 + (VIEW >> 1)] : 0;
  const [s2, s1] = WALL_TOWER[VIEW];
  const t = onTower(x + s2[0], y + s2[1]) ? 2 : onTower(x + s1[0], y + s1[1]) ? 1 : 0;
  if (t) k = wallTowerAdjust(k, t);
  if (VIEW === 2 || VIEW === 6) k = WALL_SWAP[k];
  return k;
}

function sceneWalls(out) {
  if (window.Overlays && Overlays.terrainHidden(0x4000)) return;
  const m = MAP.buildings && MAP.buildings.wall;
  if (!m || !T) return;
  if (wallCache.T !== T) {
    const tiles = [];
    for (let i = 0; i < N * N; i++) if (T.flags[i] & 0x4000) tiles.push(i);
    wallCache = { T, tiles };
  }
  for (const i of wallCache.tiles) {
    const x = i % N, y = (i / N) | 0;
    if (onTower(x, y)) continue;                  // the tower's picture stands for the wall under it (bugs.md 91)
    const sp = sprite(m.file, m.first + wallImage(x, y));
    place(out, sp, x, y, 1);                       // mirrored in views 2 and 6 like buildings (oracle rotation-walls)
  }
}

// --- avenues/boulevards: the side-strip pictures the sim exports per tile (terrain.json `avenues`,
// [tile, Zeus_General index]: the exe's rule 0x004193A0, docs/logic/avenues.md). Road tiles (< 288,
// SPR_BOUL_ROAD) are flat and drawn with the terrain (play.js buildTerrain); side strips (SPR_BOUL_SIDE_*,
// corners; some have trees or columns) are objects.
function sceneAvenues(out) {
  if (window.Overlays && Overlays.mode() === 19) return;
  const list = T && ((VIEW && T["avenues" + VIEW]) || T.avenues);   // pictures of this view (rotation.md)
  if (!list) return;
  for (const [i, idx] of list) {
    if (idx < 288) continue;
    const x = i % N, y = (i / N) | 0;
    place(out, sprite("Zeus_General", idx), x, y, 1);
  }
}

// --- gardens: SPR_GARDENS1 holds 1x1 (212-215), 2x2 (216-218) and 3x3 (219) pictures. As the exe's
// 0x00521200 (terrain pass 2, row-major, on tiles whose image is still unset; FUN_004A0FD0 checks the block
// x..x+n-1, y..y+n-1 is all garden and unset): a 3x3 if it fits, else a 2x2 (rand&3: 0,1 -> 218, 2 -> 217,
// 3 -> 216), else a 1x1 by tile parity (212 + (x&1) + 2*(y&1)). The exe's rand grid is not exported: tileRand.
let gardenCache = { S: null, stamps: [] };
function gardenStamps() {
  if (gardenCache.S === S) return gardenCache.stamps;
  const G = new Set(), used = new Set(), stamps = [];
  for (const b of S.buildings) if (b.key === "gardens") G.add(b.y * N + b.x);
  const all = (x, y, n) => { for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const k = (y + j) * N + x + i; if (x + i >= N || !G.has(k) || used.has(k)) return false; } return true; };
  for (const k of [...G].sort((a, b) => a - b)) {
    if (used.has(k)) continue;
    const x = k % N, y = (k / N) | 0, r = tileRand(x, y) & 3;
    const n = all(x, y, 3) ? 3 : all(x, y, 2) ? 2 : 1;
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) used.add((y + j) * N + x + i);
    stamps.push([x, y, n, n === 3 ? 219 : n === 2 ? (r < 2 ? 218 : r === 2 ? 217 : 216) : 212 + (x & 1) + 2 * (y & 1)]);
  }
  gardenCache = { S, stamps };
  return stamps;
}

function sceneGardens(out) {
  if (window.Overlays && Overlays.mode() && Overlays.mode() !== 17) return;
  if (!S || !T) return;
  for (const [x, y, n, idx] of gardenStamps()) place(out, sprite("Zeus_General", idx), x, y, n);
}

// --- roadblocks: not buildings in the sim, a tile list in the state (SPR_B_ROADBLOCK over the road tile)
function sceneRoadblocks(out) {
  const m = MAP.buildings && MAP.buildings.roadblock;
  if (!m || !S || !S.roadblocks || (window.Overlays && Overlays.mode() && Overlays.mode() !== 19)) return;
  for (const [x, y] of S.roadblocks) if (!(window.clearedAt && P.stateSeq < (Build.cleared || {}).seq && clearedAt(x, y))) placeSplit(out, sprite(m.file, m.base), x, y, 1);   // a flat 58x30 picture: all pass 1
}

// one building outside the state (the build preview ghost)
function drawOne(out, b, fallback) {
  if (b.key === "gardens") return place(out, sprite("Zeus_General", 212 + (b.x & 1) + 2 * (b.y & 1)), b.x, b.y, 1);
  const m = (MAP.buildings || {})[b.key];
  if (m && m.kind === "agora") return drawAgoraRoads(out, b, m, new Set());
  if (m && (m.base != null || m.front != null || m.levels || m.root || m.variants)) drawBuilding(out, b, m);
  else fallback(out, b);
}

// fishing / urchin spots (docs/play/walkers.md "Water life"): the exe's effect figures (type 6, subtypes 0x0D /
// 0x13) at the map's points, one frame every 3 game ticks from a random start, never mirrored; drawn at the
// walker spot of (x, y) + `at` tiles, + `px` (oracle water.txt, all 4 views; = walker_draw's (+2, +10) + the effect's (0, -30))
function sceneWaterLife(out) {
  const L = MAP.walkers && MAP.walkers.water_life;
  if (!L || !T) return;
  const t = Math.floor(P.t || 0);
  for (const [key, pts] of [["fish", T.fishing], ["urchin", T.urchins]]) {
    const e = L[key];
    if (!e || !pts) continue;
    for (const [x, y] of pts) {
      const c = (t + tileRand(x, y) % e.phase) % (e.frames * e.ticks_per_frame);
      const sp = sprite(e.file, e.first + Math.floor(c / e.ticks_per_frame));
      if (!sp) continue;
      // the figure stands on (x, y): sorted there, first in its tile (a fishing boat on the point draws over it,
      // bugs.md 341); `at` only moves the picture (x + 8/15 would round to the next tile)
      const fx = x + e.at[0], fy = y + e.at[1], [, cx, cy] = walkerSpot(fx, fy, { water: true });
      const d = Order.walker(x, y, { water: true, rank: -50 });
      out.push([d, fx, sp, cx + e.px[0] - sp.ax, cy + e.px[1] - sp.ay]);
    }
  }
}

window.Scene = { imageStep, walkerHits: () => WALKER_HITS, walkerAnchor: id => ANCHORS.get(id), walkerSpot, figureSpot, sceneBuildings, sceneWalkers, sceneWaterLife, sceneWalls, sceneAvenues, sceneGardens, sceneRoadblocks, roadSprite, setResources, tileRand, drawOne };
