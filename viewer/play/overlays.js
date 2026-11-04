// Map overlays of the control-panel pages ("See water", "See problems", ...): the original's view objects
// (docs/play/pages.md, data/play/overlays.json from tools/play_overlays.py). Presentation only: reads S/T and
// the overlay chosen on the panel (UIX.overlay[page]); never game rules.
// Hooks: scene.js asks hidden(b) / walkerHidden(role) / terrainHidden(flag) and skips those draws;
// play.js calls drawGround(R) after the terrain (footprints, appeal tiles) and scene(list) for the columns/panels.
"use strict";

const Overlays = (() => {
  let D = null, HOUSES = null, ground = null, groundKey = "";
  let covered = null;                             // tiles the overlay ground draws (their tall terrain is not drawn)
  // a flattened building's footprint (0x0044B050, and See security's elite pad) is drawn by ground_tile_draw 0x00457900
  // at the building's anchor cell in pass 2 step 1, like its ground: sorted with the scene at that cell's GROUND key
  // (scene() adds them), so a park or tree in front covers the house marks and one behind does not (bugs.md 428)
  let sorted = [];
  // the key of tile (x, y) of building b's footprint: GROUND of b's anchor (left corner) cell, the tiles back to front
  const footKey = (b, x, y) => {
    const k = b.corral, inC = k && x >= k[0] && x < k[0] + 4 && y >= k[1] && y < k[1] + 4;   // the corral: its own anchor
    const [w, h] = inC ? [4, 4] : dims(b), f = inC ? viewFoot(k[0], k[1], 4, 4) : viewFoot(b.x, b.y, w, h);
    const [a, c] = viewXY(x, y), [la, lc] = viewXY(f.lx, f.ly);
    return Order.cell(f.lx, f.ly, Order.GROUND, 0.001 * (a + c - la - lc + 16));
  };
  const put = (key, sp, x, y) => { if (key == null) ground.push(sp, x, y); else sorted.push([key, 0, sp, x, y]); };
  const sets = {};                                // mode -> {b: Set(zeus ids), f: Set(figure types)}
  const ROLE = {};                                // our walker role -> [figure types]
  let classOf = {};                               // zeus id -> problems class

  function init(data, houses) {
    D = data; HOUSES = houses;
    for (const [m, v] of Object.entries(D.modes)) sets[m] = { b: new Set(v.buildings), f: new Set(v.walkers) };
    Object.assign(ROLE, D.role_figures || {});
    for (const c of D.problems.classes) for (const t of c.types) classOf[t] = c.class;
  }

  const mode = () => (D && typeof UIX !== "undefined" && UIX.overlay && UIX.overlay[UIX.page]) || 0;
  const ref = r => r && sprite(r.file, r.index);
  const refK = (r, k) => r && sprite(r.file, r.index + k);
  const zid = b => {
    if (b.kind === "house") return 2 + (b.level || 0);            // house types 2..8 common, 9..14 elite
    const s = Build.cat && Build.cat[b.key];
    return s && s.zeus_id != null ? s.zeus_id : null;
  };
  const dims = b => [b.w || b.size || 1, b.h || b.size || 1];

  // --- problems (building_status_flags 0x00564560, our equivalents) -----------------------------
  const FOODS = ["urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat", "oranges"];
  function problemBits(b) {
    const ov = b.ov || {}, bits = new Set(), [fire, dmg] = ov.risk || [0, 0];
    if (fire > 800) bits.add(4);
    if (dmg > 800) bits.add(5);
    if (b.kind === "house") {
      if (!b.occupants) { bits.add(1); return bits; }
      if (b.info && b.info.code != null && b.info.code < 10) bits.add(0);     // devolving
      if ((ov.unrest || 0) > 80) bits.add(2);
      if (ov.infected) bits.add(3);
      return bits;
    }
    const spec = (Build.cat && Build.cat[b.key]) || {};
    if (spec.employees) {
      if (!b.employees || (b.info && (b.info.road === false || b.info.labor === false))) bits.add(6);
      else if (b.employees < spec.employees) bits.add(7);
      if (b.info && b.info.off) bits.add(8);
    }
    if (spec.input && (b.goods ? b.goods[spec.input] || 0 : 0) < 100) bits.add(9);
    return bits;
  }
  function problemClass(b) {
    if (b.kind === "house") return "house";
    const c = classOf[zid(b)];
    return c === "always" || !c ? "other" : c;
  }
  function shownBits(b) {                        // the bits this class shows, that are set
    const all = problemBits(b), slots = D.problems.slots[problemClass(b)] || [];
    return slots.map(g => g.filter(k => all.has(k)));
  }

  // --- visibility (+0x08 per mode) -------------------------------------------------------------
  function visible(b, m) {
    const z = zid(b);
    if (z == null) return true;
    if (z >= 100 && z <= 114) return m !== 19;               // pyramids ask their composite (always drawn)
    if (b.key === "gardens") return m === 17;                 // gardens are terrain 0x20 in the original
    if (b.kind === "wall") return !(D.modes[m].terrain_flat & 0x4000);   // walls are terrain 0x4000 there
    if (m === 7) {
      if (z === 121 || b.burning) return true;
      const [f, d] = (b.ov && b.ov.risk) || [0, 0];
      return Math.max(f, d) >= 100 && z !== 63 && z !== 64;
    }
    if (m === 18) return sets[m].b.has(z) || shownBits(b).some(g => g.length);
    return sets[m].b.has(z);
  }
  function hidden(b) { const m = mode(); return m ? !visible(b, m) : false; }
  function walkerHidden(role, id) {
    const m = mode();
    if (!m) return false;
    // See problems (+0x10 0x00564A50): carts (4/9/28/36) only while waiting (+0x7B), type 6 by its building
    if (m === 18 && role === "cart") return !(P.f0 && P.f0.waiting && P.f0.waiting.includes(id));
    const f = ROLE[role];
    return !(f && f.some(t => sets[m].f.has(t)));
  }
  function terrainHidden(flag) { const m = mode(); return m ? !!(D.modes[m].terrain_flat & flag) : false; }

  // --- ground: footprints of flattened buildings, wall tiles, appeal tiles -----------------------
  function footprintTiles(b) {                    // [x, y, sprite] (0x0044B050)
    const [w, h] = dims(b), out = footprintBox(b.x, b.y, w, h, b.kind === "house");
    // the ranch's corral (exe: its own building 0x86) is a box of its own; its tiles have no terrain picture
    // under them, so without it they were black (bugs.md 154). A dock's pier stands on water: left to the water.
    if (b.corral) out.push(...footprintBox(b.corral[0], b.corral[1], 4, 4, false));
    return out;
  }
  function footprintBox(x0, y0, w, h, house) {
    const F = D.footprint, out = [];
    if (w === 1 && h === 1) return [[x0, y0, refK(house ? F.single_house : F.single, 0)]];
    const f = viewFoot(x0, y0, w, h), [ra, rb] = viewXY(f.ax, f.ay);   // edge pieces by the box on screen (rotation.md)
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
      const [ta, tb] = viewXY(x0 + i, y0 + j), I = ta - ra, J = tb - rb, W2 = f.w, H2 = f.h;
      const k = I === 0 && J === 0 ? 0 : I === W2 - 1 && J === 0 ? 2 : I === W2 - 1 && J === H2 - 1 ? 4 : I === 0 && J === H2 - 1 ? 6
        : J === 0 ? 1 : I === W2 - 1 ? 3 : J === H2 - 1 ? 5 : I === 0 ? 7 : -1;
      const sp = k < 0 ? refK(house ? F.single_house : F.single, 1) : refK(house ? F.nw_house : F.nw, k);
      out.push([x0 + i, y0 + j, sp]);
    }
    return out;
  }
  const tilePush = (sp, x, y, key = null) => {
    if (!sp) return;
    const i = y * N + x;
    covered[i] = 1;
    const px = tileX(x, y), py = tileY(x, y) - (T.elev[i] || 0) * 30 + 30 - sp.h;
    if (key == null) flat.push([tileDepth(x, y), sp, px, py]); else put(key, sp, px, py);
  };
  // the pass-1 tiles (no building) back to front in this view, as the exe's cell walk: an appeal slab's 4 px edge
  // is covered by the tile in front of it (the grid's index order left those edges showing in views 2 / 4 / 6)
  let flat = [];
  function buildGround(m) {
    flat = [];
    buildGround0(m);
    flat.sort((a, b) => a[0] - b[0]);
    for (const [, sp, px, py] of flat) ground.push(sp, px, py);
    flat = [];
  }
  function desIndex(d) { return d <= -11 ? 0 : d < 70 ? Math.trunc(d / 10) + 2 : 9; }
  function buildGround0(m) {
    ground.clear();
    sorted = [];
    covered = new Uint8Array(N * N);
    if (!m) return;
    if (m === 17) {                               // appeal: tiles by desirability (0x0044B830)
      const A = D.appeal;
      for (let i = 0; i < N * N; i++) {
        const f = T.flags[i];
        const k = OCC ? OCC[i] : 0, b = k ? S.buildings[k - 1] : null;
        if (T.road[i] || (b && b.kind === "road")) continue;
        if ((f & 0x15361667) && !b) continue;     // water, trees, rock...: their own image
        // a building the overlay shows (parks: gardens, columns...): no slab. ground_tile_draw 0x00457900 draws nothing
        // on a garden tile (terrain 0x20) and 0x0044B050 nothing for a building whose overlay test (+0x08) shows it;
        // ours pushed a slab at each garden's own cell, which covered the front half of a garden stamp drawn at its
        // anchor (bugs.md 443, a regression of 428's sorting)
        if (b && visible(b, m)) continue;
        const x = i % N, y = (i / N) | 0;
        if (f & 0x4000) { tilePush(refK(A.wall, Scene.tileRand(x, y) & 7), x, y); continue; }
        const d = T.des ? T.des[i] : 0;
        if (!b && !(f & 0x28) && !d) continue;
        // a building's tiles: at its anchor (0x0044B050 -> 0x0044B830)
        tilePush(refK(b && b.kind === "house" ? A.house : A.other, desIndex(d)), x, y, b ? footKey(b, x, y) : null);
      }
      return;
    }
    const elite = [];
    for (const b of S.buildings) {
      if (b.kind === "road" || b.kind === "animal" || visible(b, m)) continue;
      if (m === 16 && b.kind === "house" && b.level >= 7) { elite.push(b); continue; }   // +0x0C 0x00563150: types 9..14
      for (const [x, y, sp] of footprintTiles(b)) tilePush(sp, x, y, footKey(b, x, y));
    }
    elite.sort((a, b) => tileDepth(a.x, a.y) - tileDepth(b.x, b.y));      // the ground pass runs back to front
    for (const b of elite) securityPad(b);
    if (m !== 19) for (const [x, y] of S.roadblocks || []) tilePush(refK(D.footprint.single, 0), x, y);
    if (D.modes[m].terrain_flat & 0x4000) for (let i = 0; i < N * N; i++) if (T.flags[i] & 0x4000) tilePush(refK(D.footprint.single, 0), i % N, (i / N) | 0);
  }
  // See security (16) on an elite house (exe: FUN_0044B050 calls the overlay's +0x00 = FUN_00563240 instead of the
  // footprint, for every tile of house types 9..14; it draws on the quadrant showing image 2 only): Zeus_Terrain
  // SPR_ELITE_OVERLAY 0 (an iso 4x4 pad) and rows of up to 4 figures from the counts of FUN_00563180, all in the
  // ground pass. (x, y) = that quadrant's draw point (its left tile, raised); i = x + 0x12 + 29 * (piece & 0xF) with
  // the 2x2 quadrant's piece nibble 1. Each row of n = min(count, 4) starts h = n / 2 steps right and goes 15 px
  // left / 2 px down per figure. Checked: oracle re/oracle/runs/1D-security (6 Estates, 4 chariots each).
  function soldierCounts(b) {                     // FUN_00563180: [spare armour, spare horses, unarmed, hoplites, chariots]
    const H = HOUSES && HOUSES[b.level], g = b.goods || {}, arms = g.armor || 0, horses = g.horses || 0;
    let need = Math.ceil((b.occupants || 0) * ((H && H.soldier_pct) || 0) / 100);
    const ch = Math.min(need, b.level === 12 ? Math.min(arms, horses) : 0);   // chariots: type 0xE (Estate) only
    need -= ch;
    const hop = Math.min(need, arms - ch);
    return [arms - ch - hop, horses - ch, need - hop, hop, ch];
  }
  function securityPad(b) {
    const E = D.security_elite, pic = k => E && sprite(E.file, E.index + k);
    const q = [[2, 2], [0, 2], [0, 0], [2, 0]][(VIEW >> 1) & 3];   // the quadrant showing image 2 (scene.js elite house)
    const f = viewFoot(b.x + q[0], b.y + q[1], 2, 2), lx = f.lx, ly = f.ly;
    const x = tileX(lx, ly), y = tileY(lx, ly) - (T.elev[ly * N + lx] || 0) * 30, i = x + 0x12 + 29, key = Order.cell(lx, ly, Order.GROUND);
    for (let dy = 0; dy < 4; dy++) for (let dx = 0; dx < 4; dx++) covered[(b.y + dy) * N + b.x + dx] = 1;
    const pad = pic(0);
    if (pad) put(key, pad, x + 30 - 90, y - 0x4b + 120 - pad.h);     // iso picture of 4: left - 30 (n - 1), top + 30 n - h
    const [armour, horses, unarmed, hop, ch] = soldierCounts(b), flip = viewMirror() ? -1 : 1;
    const row = (k, n, x0, y0) => {             // n figures from (x0, y0), 15 px left and 2 px down each
      const sp = pic(k);
      if (sp) for (let j = 0; j < Math.min(n, 4); j++) put(key, sp, x0 - 15 * j, y0 + 2 * j);
    };
    const h = n => Math.min(n, 4) >> 1;
    if (unarmed > 0) row(2, unarmed, i + 15 * h(unarmed), y - 0x4e - (2 * h(unarmed) + 10));
    if (armour > 0) row(1, armour, i - 0x3c * flip + 15 * h(armour), y - 0x30 + (6 - h(armour)) * 2);
    if (horses > 0) row(5, horses, i + 0x3c * flip + 15 * h(horses) - 15, y - 0x30 - 2 * h(horses) - 5);
    const both = ch > 0 && hop > 0;
    if (ch > 0) row(4, ch, (both ? i - 10 : i - 5) + 15 * h(ch), (both ? y - 0x26 : y - 0x20) - 2 * h(ch));
    if (hop > 0) row(3, hop, i - 5 + 15 * h(hop), (both ? y - 0x1a : y - 0x20) - 2 * h(hop));
  }

  function ensureGround(m) {                       // false: nothing to draw yet
    if (!D || !S || !T || typeof R === "undefined") return false;
    if (!ground) ground = R.batch();
    const key = m + ":" + (S.seq || S.tick || 0) + ":" + S.buildings.length + ":" + (T.map_version || 0) + ":" + VIEW;   // positions per view
    if (key !== groundKey) { groundKey = key; buildGround(m); }
    return true;
  }
  function drawGround() {
    const m = mode();
    if (ensureGround(m) && m) ground.draw();
  }

  // --- columns and panels on buildings ----------------------------------------------------------
  function anchor(b) {                            // the original's draw point: the left tile (x, y+h-1), raised
    const [w, h] = dims(b), f = viewFoot(b.x, b.y, w, h), x = f.lx, y = f.ly;   // left corner in this view
    return [tileX(x, y), tileY(x, y) - (T.elev[y * N + x] || 0) * 30];
  }
  function column(out, depth, n, style, x, y) {   // 0x0055EC00
    const C = D.column.sprite;
    n = Math.max(0, Math.min(10, n | 0));
    const c = style === 2 ? 12 : style === 0 ? 0 : n >= 9 ? 9 : n >= 7 ? 6 : n >= 5 ? 3 : 0;
    const top = refK(C, c), mid = refK(C, c + 1), base = refK(C, c + 2);
    if (base) out.push([depth, 0, base, x + 9, y - 8]);
    if (!n || !top) return;
    out.push([depth, 0, top, x + 5, y - 10 * n - top.h + 15]);
    if (mid) for (let k = 0; k < n - 1; k++) out.push([depth, 0, mid, x + 17, y - 5 - 10 * k]);
  }
  function columnValue(b, M) {
    const ov = b.ov || {}, cov = b.coverage || {};
    switch (M.field) {
      case "coverage.water": return b.level >= 7 ? 100 : cov.water || 0;     // elite houses: 10 (0x00560410)
      case "risk": return Math.max(...((ov.risk) || [0, 0]));
      case "unrest": return ov.unrest != null ? ov.unrest : (b.info && b.info.unrest) || 0;
      case "tax_days": return ov.tax != null ? ov.tax : (b.info && b.info.taxed ? 50 : 0);
      case "culture": return ov.culture || 0;
      default: return M.field.startsWith("coverage.") ? cov[M.field.slice(9)] || 0 : null;
    }
  }
  function supplies(out, depth, b, x, y) {        // 0x0055F5A0
    const U = D.supplies, elite = b.level >= 7, H = HOUSES && HOUSES[b.level], H1 = HOUSES && HOUSES[Math.min(b.level + 1, elite ? 12 : 6)];
    const bg = ref(elite ? U.bg6 : U.bg3);
    if (bg) out.push([depth, 0, bg, x + 11, y - 16]);
    const lowT = elite ? U.exe_tables.low_elite[Math.max(0, b.level - 9)] : U.exe_tables.low_common[b.level];
    const g = b.goods || {}, blink = (performance.now() & 0x200) !== 0;
    const lows = lowSlots(b);
    for (let i = 0; i < (elite ? 6 : 3); i++) {
      const need = U.slot_needs[i];
      if (H && H1 && !H[need] && !H1[need]) continue;
      const good = U.slot_goods[i];
      const grp = lows.includes(i) ? (blink ? U.low_on : U.low_off) : U.ok;
      const sp = refK(grp, U.icon[good]);
      if (sp) out.push([depth, 0, sp, x + 21 + 26 * i, y - 6]);
    }
  }
  function lowSlots(b) {                          // supply slots needed now or at the next level and low (0x0055F440)
    const U = D.supplies, elite = b.level >= 7, H = HOUSES && HOUSES[b.level], H1 = HOUSES && HOUSES[Math.min(b.level + 1, elite ? 12 : 6)];
    const lowT = elite ? U.exe_tables.low_elite[Math.max(0, b.level - 9)] : U.exe_tables.low_common[b.level];
    const g = b.goods || {}, out = [];
    for (let i = 0; i < (elite ? 6 : 3); i++) {
      const need = U.slot_needs[i];
      if (H && H1 && !H[need] && !H1[need]) continue;
      const good = U.slot_goods[i];
      const have = good === "food" ? FOODS.reduce((s, f) => s + (g[f] || 0), 0) : g[good] || 0;
      if (lowT && have <= lowT[i]) out.push(i);
    }
    return out;
  }
  function problems(out, depth, b, x, y) {        // 0x00565030
    const P_ = D.problems, cls = problemClass(b), groups = shownBits(b);
    if (!groups.some(g => g.length)) return;
    const bg = ref(P_.bg[cls]);
    if (bg) out.push([depth, 0, bg, x, y]);
    const k = cls === "house" ? 2 : 10;
    groups.forEach((g, s) => {
      for (const bit of g) { const sp = refK(P_.icons, bit); if (sp) out.push([depth, 0, sp, x + k + 26 * s, y + k]); }
    });
  }
  // the waiting cart's '?' (0x00564B00: SPR_PROBLEM_ICONS + 11). Overlays 2, 3 have the method too, but their +0x14
  // (0x0055FFA0) needs the walker test +0x10, which carts fail there: only See problems shows it
  function cartIcon() { return D && mode() === 18 ? refK(D.problems.icons, 11) : null; }
  function scene(out) {
    const m = mode();
    if (!m || !D || !S) return;
    const M = D.modes[m];
    if (ensureGround(m)) for (const e of sorted) out.push(e);   // footprints (buildGround), at their anchors' GROUND
    for (const b of S.buildings) {
      if (b.kind === "road" || b.kind === "animal" || !visible(b, m)) continue;
      const [w, h] = dims(b), [x, y] = anchor(b);
      const depth = M.last_pass ? Order.LAST + tileDepth(b.x, b.y) : Order.obj(b.x, b.y, w, h);   // pass 3 / after its building (push order)
      const house = b.kind === "house";
      if (M.kind === "column") {
        if (m === 15) {                           // immortals (0x00562E70 / +0x0C 0x00562E10): a complete sanctuary's
          // column n = activity (root +0x32) / 2, style 0, on its altar part (sanctuary_altar_part 0x004EA390)
          const z = zid(b), pp = z >= 84 && z <= 98 && (b.built || 0) >= 100 && window.Monuments && Monuments.piecePoint(b, 2, MCTX);
          if (pp) column(out, pp[2], ((b.info && b.info.activity) || 0) >> 1, 0, pp[0], pp[1]);
          continue;
        }
        if (m === 7) {
          const v = columnValue(b, M);
          if (v >= 100) column(out, depth, v / M.div, M.style, x, y);
          continue;
        }
        if (!house) continue;
        column(out, depth, columnValue(b, M) / M.div, M.style, x, y);
        if (m === 6 && b.ov && b.ov.fed) { const sp = ref(D.hygiene_food.sprite); if (sp) out.push([depth, 0, sp, x + 20, y]); }
      } else if (M.kind === "supplies") {
        if (house && b.occupants) supplies(out, depth, b, x, y);
      } else if (M.kind === "problems") {
        problems(out, depth, b, x, y);
      }
    }
  }

  // --- minimap under an overlay (minimap_draw 0x00454980 -> view object +0x24 0x0055F250; pages.md) ---------------
  // a building's colour: road (avenue, boulevard, agoras), then red (+0x28), green (+0x30), purple (+0x2C), else
  // black; overlays.json modes[m].minimap groups give each type's colour, a band of a field, or problem / none
  const MM_ORDER = ["road", "red", "green", "purple", "black"];
  function fieldValue(b, field) {
    if (field.startsWith("max(risk")) return Math.max(...((b.ov && b.ov.risk) || [0, 0]));
    if (field.startsWith("sanctuary_activity")) return (b.info && b.info.activity) || 0;   // root +0x32 (sim/gods)
    return columnValue(b, { field }) || 0;
  }
  const band = (bands, v) => { const r = bands.find(([lo, hi]) => v >= lo && v <= hi); return r ? r[2] : null; };
  function minimapColour(b) {                     // [[r, g, b], [r, g, b]] (the image's first two pixels) or null
    const m = mode();
    if (!m || !D || !D.minimap) return null;
    const pal = D.minimap.palette, M = D.modes[m].minimap;
    if (b.kind === "wall") return pal.black.rgb;  // terrain 0x4000 in the exe: SPR_R_FIRST_BUILD+60 in every overlay
    const z = zid(b), got = new Set();
    if (z != null && M) for (const g of M.groups) {
      if (!g.types.includes(z)) continue;
      if (g.colour) got.add(g.colour);
      else if (g.bands) { const c = band(g.bands, fieldValue(b, g.field)); if (c) got.add(c); }
      else if (g.problem) got.add(shownBits(b).some(x => x.length) ? g.problem : g.no_problem);
    }
    const c = MM_ORDER.find(k => got.has(k)) || "black";
    return pal[c].rgb;
  }
  // appeal (17): every tile with a building or a desirability != 0 by the main view's SPR_DES index (0x0044BCF0)
  function minimapAppeal(i, b) {
    if (mode() !== 17 || !D || !D.minimap) return null;
    const d = T.des ? T.des[i] : 0;
    if (!b && !d) return null;
    return D.minimap.palette.appeal[desIndex(d)].rgb;
  }

  // --- hover tooltip (+0x1C, called every frame by 0x004F6A10 with an overlay on; pages.md) -----------------
  // returns the text ('@L' ends a line) for the tile under the mouse, or null
  // '@L' is a line break only as a word of its own (text_layout 0x004F5300 / panelWord): spaced here
  const TT = s => s.replace(/\{(\d+):(\d+)\}/g, (_, g, i) => (D.tooltip.texts[`${g}:${i}`] || "")).replace(/ *@L */g, " @L ").trim();
  function tooltipAt(x, y) {
    const m = mode();
    if (!m || !D || !D.tooltip || !S || !T) return null;
    const M = D.modes[m], tt = M.tooltip;
    if (!tt) return null;
    const i = y * N + x, b = buildingAt(x, y), z = b ? zid(b) : null;
    if (m === 17) { const t = band(tt.bands, T.des ? T.des[i] : 0); return t ? TT(t) : null; }   // any tile
    // no building: a waiting cart on the tile (0x00565360: types 4/9/28/36, +0x7B) -> 66:16 (2/3: 0x0055FF50 asks +0x14,
    // false for carts there)
    if (m === 18 && (!b || b.kind === "road") && P.f0 && P.f0.waiting && P.f0.waiting.length) {
      const W = new Set(P.f0.waiting);
      if (P.f0.walkers.some(w => w[1] === x && w[2] === y && W.has(w[0]))) return TT("{66:16}");
    }
    if (!b || b.kind === "road" || b.kind === "animal") return null;
    const house = b.kind === "house";
    if (m === 1 || m === 4) {                     // supplies: the low needed goods (0x0055FB20)
      if (!house || !b.occupants) return null;
      const lows = lowSlots(b);
      return lows.length ? TT("{66:1}@L" + lows.map(k => `{${tt.slot_text[k][0]}:${tt.slot_text[k][1]}} `).join("")) : TT("{66:3}");
    }
    if (m === 2 || m === 3 || m === 18) {         // problems: 66:4 then 66:(5 + bit) per set bit, slot order
      if (m !== 18 && !sets[m].b.has(z)) return null;
      const bits = shownBits(b).flat();
      return bits.length ? TT("{66:4}@L" + bits.map(k => `{66:${5 + k}}@L`).join("")) : null;
    }
    if (m === 7) {                                // hazards: any building (0x00560F10)
      if (b.burning) return TT(tt.burning);
      const [f, dm] = (b.ov && b.ov.risk) || [0, 0], v = Math.max(f, dm);
      const k = v <= 100 ? 0 : v <= 200 ? 1 : v <= 400 ? 2 : v <= 600 ? 3 : v <= 800 ? 4 : 5;
      return TT(`{66:${(f > dm ? 28 : 35) + k}}`);
    }
    if (m === 15) {                               // immortals: a completed sanctuary (column part not tested)
      if (!(z >= 84 && z <= 98) || (b.built || 0) < 100) return null;
      const t = band(tt.bands, fieldValue(b, tt.field));
      return t ? TT(t) : null;
    }
    if (m === 5 && house && b.level >= 7) return TT(tt.elite);   // elite houses: 66:17 (exe: their picture tile only)
    if (m === 16) return house && b.level >= 7 ? securityTip(b, x, y) : null;
    const g = (tt.groups || []).find(g => g.types.includes(z) || (m === 6 && house));   // hygiene: elite houses too
    if (!g) return null;
    if (m === 6) { const t = band(g.bands, fieldValue(b, g.field)); return t ? TT(t.split("@L")[0] + "@L" + tt.line2.values[b.ov && b.ov.fed ? 1 : 0]) : null; }
    const t = band(g.bands, fieldValue(b, g.field));     // taxes: the exe prints "N drachmas paid" first when the
    return t ? TT(t) : null;                              // house paid this year (not exported: coverage bands)
  }

  // See security's tooltip (+0x1C 0x005638A0, disassembled 10-30): by the elite house quadrant under the mouse, i.e.
  // the picture offset the picture grid 0x00D4CFC8 holds there (scene.js: quadrant k shows image [2, random bit, 3,
  // 4][k'], k' = k with 1 and 3 swapped in views 2 / 6), with FUN_00563180's counts (soldierCounts); first that
  // applies: offset 1 and spare armour: 66:83 'This house has ' N 66:86/87; offset 4 and spare horses: 66:83 N
  // 66:84/85; offset 3 and warriors lacking armour: N 66:81/82; offset 2 (tile_ground_image_test 0x00565760) and
  // soldiers: H 66:88/89 [66:2 ' and' ' '] P 66:91/90 + 66:98 (H + P > 1) / 66:99 (plural when N > 1, singular
  // N = 1); else none. Poseidon's chariot / spearman texts (92..97) are not used outside Poseidon games.
  function securityTip(b, x, y) {
    const dx = (x - b.x) >= 2 ? 2 : 0, dy = (y - b.y) >= 2 ? 2 : 0, Q = [[2, 2], [0, 2], [0, 0], [2, 0]];
    const T4 = [2, tileRand(b.x, b.y) & 1, 3, 4];
    let off = null;
    for (let k = 0; k < 4; k++) {
      const q = Q[(k + (VIEW >> 1)) & 3];
      if (q[0] === dx && q[1] === dy) off = T4[viewMirror() && (k & 1) ? k ^ 2 : k];
    }
    const [armour, horses, unarmed, hop, ch] = soldierCounts(b), n = v => String(Math.trunc(v));
    if (off === 1 && armour) return TT(`{66:83}${n(armour)}{66:${armour === 1 ? 87 : 86}}`);
    if (off === 4 && horses) return TT(`{66:83}${n(horses)}{66:${horses === 1 ? 85 : 84}}`);
    if (off === 3 && unarmed) return TT(`${n(unarmed)}{66:${unarmed === 1 ? 82 : 81}}`);
    if (off !== 2 || !(ch || hop)) return null;
    let s = "";
    if (ch) s = `${n(ch)}{66:${ch > 1 ? 88 : 89}}` + (hop ? "{66:2} " : "");
    if (hop) s += `${n(hop)}{66:${hop > 1 ? 91 : 90}}`;
    return TT(s + `{66:${ch + hop > 1 ? 98 : 99}}`);
  }

  // data: the exe's tables and the house levels' needs (supplies slots)
  Promise.all([fetch("/data/play/overlays.json").then(r => r.json()), fetch("/data/houses.json").then(r => r.json()).catch(() => null)])
    .then(([d, h]) => init(d, h)).catch(e => console.error("overlays:", e));

  // a terrain picture taller than its tile (TALL in play.js: some scrub/meadow variants are 31 px) is drawn in the
  // object pass, over the overlay ground: on a tile the overlay ground covers it must go, as the exe's overlay tile
  // replaces the tile's image (bugs.md 139: grass patches on a vacant elite lot in the appeal overlay)
  function covers(t) { return !!(t && mode() && covered && covered[t[1] * N + t[0]]); }

  return { init, mode, hidden, walkerHidden, terrainHidden, drawGround, scene, problemBits, covers, minimapColour, minimapAppeal, cartIcon,
           tooltipAt, key: () => mode() + ":" + ((typeof S !== "undefined" && S && (S.seq || S.tick)) || 0) };
})();
window.Overlays = Overlays;
