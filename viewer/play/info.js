// Building info window contents (right click on a building), per building type, after Zeus.exe's panel
// functions (docs/play/info.md; layouts and strings: data/play/info_panels.json from tools/play_info.py).
// Presentation only: every value comes from the server's building record (sim/export.py, `info` extras);
// nothing here computes game rules. ui.js owns the window (frame, placement, help/close buttons) and calls
//   ZInfo.size(b)                 -> {cols, rows} of the window for this building
//   ZInfo.draw(b, L, T, cols, rows) draws the contents with ui.js's uiText / uiPut / uiFrame.
// Positions are the exe's, relative to the window's top-left (L, T).
"use strict";

const ZInfo = (() => {
  let D = null;
  const FONT = f => "SPR_FONTS_" + f;
  const txt = (g, i) => (D && D.texts[String(g)] && D.texts[String(g)][i]) || "";
  const panelOf = b => (D && D.panels[b.key]) || null;
  const spec = b => (typeof Build !== "undefined" && Build.cat && Build.cat[b.key]) || {};
  const ready = () => !!(D && window.ZText);

  // pen arithmetic of the exe (0x00F13A70): each piece moves the pen by its advance + one space
  const cursor = (font, s) => ZText.advance(FONT(font), s) + ZText.advance(FONT(font), " ");
  // a chain of pieces drawn at x + pen (pen cumulative; {dx} shifts the base like the exe's second base x)
  function chain(x, y, font, parts) {
    let p = 0;
    for (const s of parts) {
      if (s == null || s === "") continue;
      if (typeof s === "object") { x += s.dx || 0; continue; }
      uiText(s, x + p, y, FONT(font));
      p += cursor(font, s);
    }
    return p;
  }
  const num = (n, sign = "@", suffix = " ") => ZText.numberText(n, sign, suffix);
  // count_noun_draw 0x00508DD0: " n" then group g index k (n == +-1) or k + 1
  const countNoun = (n, g, k) => [num(n, n < 0 ? "-" : " ", ""), txt(g, k + (Math.abs(n) === 1 ? 0 : 1))];
  const para = (str, x, y, w, font = "11C") => uiText(str, x, y, FONT(font), { width: w });
  const line = (str, x, y, font = "11C") => uiText(str, x, y, FONT(font));
  const center = (str, x, y, w, font) => uiText(str, x, y, FONT(font), { center: w });
  const ref = (r, g) => Array.isArray(r) ? txt(r[0], r[1]) : txt(g, r);

  function icon(good) {                            // goods icon (SPR_GOODS_ICONS / Poseidon icons)
    const r = D.goods_icons[good];
    return r ? sprite(r.file, r.index) : null;
  }

  // RIMS highlight rectangle (0x0059F6E0): edges only, last tile pulled back so the rect is exact
  function rims(x, y, w, h, hover) {
    const base = UIX.D.frames.highlight.sprite_group.index + (hover ? 8 : 0);
    const nc = Math.ceil(w / 16), nr = Math.ceil(h / 16);
    for (let c = 0; c < nc; c++) {
      const tx = c === nc - 1 ? x + w - 16 : x + 16 * c;
      uiPut(sprite("Zeus_Interface", base + (c === 0 ? 0 : c === nc - 1 ? 2 : 1)), tx, y);
      uiPut(sprite("Zeus_Interface", base + (c === 0 ? 6 : c === nc - 1 ? 4 : 5)), tx, y + h - 16);
    }
    for (let r = 1; r < nr - 1; r++) {
      uiPut(sprite("Zeus_Interface", base + 7), x, y + 16 * r);
      uiPut(sprite("Zeus_Interface", base + 3), x + w - 16, y + 16 * r);
    }
  }

  // --- shared state readers -----------------------------------------------------------------------
  const I = b => b.info || {};
  const noRoad = b => I(b).road === false || b.reason === "no road access";
  const noLabor = b => I(b).labor === false || /^no workers can reach/.test(b.reason || "");
  const need = b => spec(b).employees || 0;
  const pop = () => (P && P.f0 && P.f0.population) || 0;

  // staffing state in the exe's order (0x00577D20): fire, road, labour pool, halted, none, %
  function staffKey(b, L) {
    if (b.burning) return "fire";
    if (noRoad(b)) return "no_road";
    if (noLabor(b)) return "no_labor";
    if (I(b).off && L.halted != null) return "halted";
    const n = need(b), e = b.employees || 0;
    if (n && e <= 0) return "none";
    const pct = n ? (e * 100) / n : 100;
    return pct >= 100 ? "s100" : pct >= 75 ? "s75" : pct >= 50 ? "s50" : pct >= 25 ? "s25" : "s0";
  }
  function ladderText(b, p, key) {
    const L = p.ladder || D.panels.road.ladder;
    if (key === "no_road") return [txt(69, 4), "11C"];
    if (key === "no_labor") return [txt(69, 5), "11C"];
    let v = L[key];
    if (v == null && /^s/.test(key)) v = L.s100;          // ladders with fewer steps
    if (v == null) return ["", "11C"];
    return [ref(v, p.group), "11C"];
  }

  // workers line 0x00577290 (y0 = the exe's argument)
  function workers(b, L, y0, needN, emp) {
    const C = D.layouts.common.workers;
    const n = needN != null ? needN : need(b), e = emp != null ? emp : (b.employees || 0);
    if (n + e === 0) return;
    let k = 0;
    if (e < n) k = pop() < 1 ? 1 : noRoad(b) ? 2 : 3;
    uiPut(sprite(D.icons.workers.file, D.icons.workers.index), L + C.icon_dx, y0 + C.icon_dy);
    const y = y0 + (k ? C.dy_short : C.dy_full);
    chain(L + C.text_dx, y, C.font, [...countNoun(e, 8, 12), { dx: C.need_dx - C.text_dx }, num(n, "(", " "), txt(69, 0)]);
    if (k) para(txt(69, k), L + C.reason_dx, y0 + C.reason_dy, C.reason_w, C.font);
  }

  const inset = (L, T, cols, p) => p.inset && uiFrame("plain", L + 16, T + p.inset[0], cols - 2, p.inset[1]);
  const yOf = (T, rows, y) => (y < 0 ? T + rows * 16 + y : T + y);
  function title(b, p, L, T, cols, idx = 0) {
    const s = p.title_ref ? ref(p.title_ref) : p.group != null ? txt(p.group, p.title_index != null ? p.title_index : idx)
      : txt(28, p.zeus_id) || spec(b).name || b.key;
    center(s, L, T + 10, cols * 16, "22C");
  }
  function desc(p, L, T, cols, rows) {
    if (p.desc_y == null || p.group == null) return;
    para(txt(p.group, p.desc_index != null ? p.desc_index : 1), L + 32, yOf(T, rows, p.desc_y), (cols - 4) * 16);
  }
  function status(b, p, L, T, cols, rows, key) {
    const [s, f] = ladderText(b, p, key || staffKey(b, p.ladder || {}));
    para(s, L + 32, yOf(T, rows, p.status_y), (cols - 4) * 16, f);
  }

  // --- panels -------------------------------------------------------------------------------------
  const PANELS = {};

  // services / generic: title, status ladder, inset + workers (+ description)
  PANELS.service = PANELS.generic = PANELS.walker = PANELS.venue = (b, p, L, T, cols, rows) => {
    title(b, p, L, T, cols);
    let key = staffKey(b, p.ladder || {});
    const out = I(b).out;
    if (p.panel === "walker" && /^s/.test(key)) {   // walker state first (0x0057BE20: out / preparing), then staffing
      para(ref(out ? p.ladder.out : p.ladder.idle, p.group), L + 32, T + p.status_y, (cols - 4) * 16);
      const [s] = ladderText(b, p, key);
      para(s, L + 32, T + p.status2_y, (cols - 4) * 16);
    } else {
      if (p.panel === "venue" && /^s/.test(key) && p.ladder.s100 != null) key = "s100";
      status(b, p, L, T, cols, rows, key);
    }
    inset(L, T, cols, p);
    workers(b, L, T + p.workers_y);
    desc(p, L, T, cols, rows);
  };

  // fountain 0x0057D750: status 108:(workers + 2) (fire 111:1), inset at +0x68
  PANELS.fountain = (b, p, L, T, cols, rows) => {
    title(b, p, L, T, cols);
    const key = staffKey(b, {});
    const s = key === "fire" ? txt(111, 1) : key === "no_road" ? txt(69, 4) : key === "no_labor" ? txt(69, 5)
      : txt(p.group, Math.min(4, b.employees || 0) + 2);
    para(s, L + 32, yOf(T, rows, p.status_y), (cols - 4) * 16);
    inset(L, T, cols, p);
    workers(b, L, T + p.workers_y);
  };

  // decorations 0x00577A10: 137:2k title, 137:2k+1 at T+0x38
  PANELS.decor = (b, p, L, T, cols) => {
    center(txt(137, 2 * p.k), L, T + 10, cols * 16, "22C");
    para(txt(137, 2 * p.k + 1), L + 32, T + 0x38, (cols - 4) * 16);
  };

  // title + description (columns, avenue, roadblock, gatehouse, rubble, palace, commemorative)
  PANELS.simple = (b, p, L, T, cols, rows) => {
    title(b, p, L, T, cols);
    if (p.desc_y_top != null) para(txt(p.group, 1), L + 32, T + p.desc_y_top, (cols - 4) * 16);
    else if (p.desc_y == null)                    // commemorative: text 90:variant (0x00577C50)
      para(txt(p.group, p.desc_variant ? b.variant || 1 : p.desc_index || 1), L + 32, T + 0x38, (cols - 4) * 16);
    else desc(p, L, T, cols, rows);
    if (need(b) && !p.no_workers) { const y = rows * 16 - 128; uiFrame("plain", L + 16, T + y, cols - 2, 4); workers(b, L, T + y + 6); }
  };

  // walker list of the locality (0x00573540; we list nobody: the inset shows 70:0 only when no walker
  // stands on the building, else stays empty) + description (avenue, boulevard, park)
  PANELS.locality = (b, p, L, T, cols, rows) => {
    title(b, p, L, T, cols);
    uiFrame("plain", L + 16, T + 0x28, cols - 2, 12);
    const ws = (P && P.f0 && P.f0.walkers) || [];
    const w = b.w || b.size || 1, h = b.h || b.size || 1;
    if (!ws.some(q => q.x >= b.x && q.x < b.x + w && q.y >= b.y && q.y < b.y + h)) center(txt(70, 0), L, T + 0x78, cols * 16, "11CB");
    para(p.desc_ref ? ref(p.desc_ref) : txt(p.group, 1), L + p.desc_x, yOf(T, rows, p.desc_y), (cols - 4) * 16);
  };

  // sanctuaries / pyramids (0x005813F0): title, staffing, the god's three texts, the prayer button, workers box
  // (Oracle of Apollo seen); sacrifices, the oracle button and god states are not shown. Under construction
  // (monument_progress < 100) the window is the exe's first branch: no god text, no prayer, no workers box.
  const tok = (s, t) => s.replace(/\[(\w+)\]/g, (m, k) => (t[k] != null ? String(t[k]) : m));   // FUN_00466B50
  let prayRes = null;                            // {id, win, code}: the window's prayer result (DAT_00FFA184)
  async function pray(b, g) {
    const win = UIX.info;
    prayRes = { id: b.id, win, code: 0 };
    try {
      const r = await postCmds([`pray ${g}`]);
      const m = /^result (\d)/.exec(((r.results || [])[0] || {}).out || "");
      if (prayRes && prayRes.win === win) prayRes.code = m ? +m[1] : 3;
    } catch (e) { toast("pray: server unreachable", true); }
  }
  PANELS.monument = (b, p, L, T, cols, rows) => {
    const M = D.layouts.sanctuary, w = cols * 16 - M.w_less, X = L + M.x;
    const W = I(b).build;
    if (W) return monumentBuild(b, p, L, T, cols, M, W);
    center(txt(28, p.zeus_id) || spec(b).name, X, T + M.title_y, w, "22C");
    let y = T + M.status_y;
    const ws = (cols - 4) * 16, pf = (s, x, yy, ww) => { para(s, x, yy, ww); return 16 * ZText.wrap(FONT("11C"), s, ww).length; };
    const built = b.built != null ? b.built : 100;
    let blocked = false, under = false;          // local_a06 (no road / no staff: no buttons), bVar4 (understaffed)
    if (built < 100) { para(`${built}%`, X, y, w); y += 16 + 16; }        // a server without info.build
    else {                                       // staffing (0x005813F0 second branch): full staff draws nothing
      const n = need(b), e = b.employees || 0, pct = n ? (e * 100) / n : 100;
      let s = null;
      if (noRoad(b)) { s = txt(69, 4); blocked = true; }
      else if (noLabor(b)) { s = txt(69, 5); blocked = true; }
      else if (n && e < 1) { s = txt(132, 0); blocked = true; }
      else if (pct < 100) { s = txt(132, pct >= 75 ? 1 : pct >= 50 ? 2 : pct >= 25 ? 3 : 4); under = true; }
      if (s) y += pf(s, L + 32, y, ws) + 16;
      if (!blocked && !under) {                  // sacrifices: conducting 132:7, priests out 132:6, else by the
        const a = I(b).activity != null ? I(b).activity : 22;   // activity counter +0x32: < 19 -> 132:108, else 132:9
        const k = I(b).sacrificing ? 7 : I(b).priests_out ? 6 : a < 19 ? 108 : 9;
        y += pf(txt(132, k), X, y, w) + 16;
      }
    }
    const g = p.god;
    if (g != null) {
      const d = [M.text1, M.text2, M.text3].map(k => txt(132, g + k)).join(" ");
      para(d, X, y, w);
      // buttons (FUN_0057CD10, FUN_0057CCA0): none while blocked; the prayer (table 0x005EFA88 row 0 at
      // (L+0x4B, T+200+140)), and for a god with an oracle (Zeus, Apollo: god_has_oracle 0x004EA600) row 1 at
      // T+200+40 "Consult Oracle" 132:109 (132:110 Oracle Unavailable, no hover, when used up: not simulated)
      if (!blocked && built >= 100) {
        const btn = (r, label, onClick) => {
          const [bx, by, bw, bh] = r, hov = !!onClick && uiHover(L + bx, T + by, bw, bh);
          rims(L + bx, T + by, bw, bh, hov);
          para(label, L + bx + M.pray_label[0], T + by + M.pray_label[1], cols * 16 - 30);
          if (onClick) UIX.hits.push([L + bx, T + by, bw, bh, onClick, label]);
        };
        // the prayer (sanctuary_pray_click 0x00408DA0 -> sim `pray`): its result DAT_00FFA184 (reset when a window
        // opens) is drawn at (X, T + 0x127) in w: 132:god+0x26 heard / +0x18 granted (font 2 = 11C), +0x34 refused
        // (font 10 = 11LTYEL)
        if (prayRes && (prayRes.win !== UIX.info || prayRes.id !== b.id)) prayRes = null;
        btn(M.pray, txt(132, M.pray_text + g), () => pray(b, g));
        if (prayRes && prayRes.code) {
          const k = { 1: 0x26, 2: 0x18, 3: 0x34 }[prayRes.code];
          para(txt(132, g + k), X, T + 0x127, w, prayRes.code === 3 ? "11LTYEL" : "11C");
        }
        // Consult Oracle 132:109 (wm_sub_408EB0 -> sim `oracle`), or 132:110 Oracle Unavailable without hover
        // when the god's oracle counter has reached its threshold (oracle_consult(1, 1); info.oracle)
        if (g === 0 || g === 3) {
          const ok = I(b).oracle !== false;
          btn(M.oracle, txt(132, ok ? 109 : 110), ok ? () => sendCommands([`oracle ${g}`], { sound: false }) : null);
        }
      }
    }
    uiFrame("plain", L + 16, yOf(T, rows, p.inset[0]), cols - 2, p.inset[1]);
    workers(b, L, yOf(T, rows, p.workers_y));
  };

  // monument under construction (0x005813F0 first branch; data sim/systems/monuments.py window(), seen:
  // re/oracle/runs/sanctuary-window/b.bmp). Paragraphs at L+0x14, width C*16-0x1E, font 11C, step 16.
  function monumentBuild(b, p, L, T, cols, M, W) {
    const B = M.build, X = L + M.x, w = cols * 16 - M.w_less;
    const name = txt(28, p.zeus_id) || spec(b).name, god = p.god != null ? txt(157, p.god) : "";
    const t = { monument: name, god, percent_complete: `${W.pct}%` };
    uiText(tok(ref(B.title), t), X, T + M.title_y, FONT("22C"), { width: w, align: "center", wrap: true });
    const h = s => 16 * ZText.wrap(FONT("11C"), s, w).length;      // DAT_00F13A6C after a paragraph
    const pf = (s, y) => { para(s, X, y, w); return h(s); };
    let y = T + B.body_y;
    if (!W.road) y += pf(txt(69, 4), y);                            // 0x00FFA144 < 1
    else if (W.halted) y += pf(ref(W.artisans < 1 ? B.halted : B.halted_working), y);
    else if (W.guilds < 1) y += pf(ref(B.no_guild), y);
    else if (W.artisans < 1) y += pf(ref(B.no_artisans), y);
    else for (const k of B.check_order) {                          // the parts being worked need it now
      if (!(W.now[k] > 0)) continue;
      const i = W.stock[k] < 400 ? B.none[k] : W.stockpiled.includes(k) ? B.stockpiled[k]
        : W.short.includes(k) ? B.undeliverable[k] : null;
      if (i != null) y += pf(txt(178, i), y);
    }
    let y7 = y + 16;
    if (W.artisans > 0) {
      const s = tok(txt(178, B.activity[String(W.kind)] || B.activity["1"]), t);
      y7 = y + 32 + pf(s, y7);
    }
    const pc = tok(txt(178, B.percent), t);
    y7 += 16 + pf(pc, y7);
    const ld = W.loads || {};
    if (B.loads_order.every(k => !ld[k])) pf(txt(178, B.arrived), y7);
    else {
      y7 += pf(txt(178, B.remainder), y7);
      for (const k of B.loads_order) {
        const n = ld[k] || 0;
        if (n > 0) y7 += pf(tok(txt(178, B.loads[k] + (n > 1 ? 1 : 0)), { amount: n }), y7);
      }
    }
    // Halt / Resume Construction (FUN_0057CD10, table 0x005EFAC0 at (L+0x4B, T+200) + (0, 240); click 0x00408E40)
    const [bx, by, bw, bh] = B.halt, hx = L + bx, hy = T + by, hov = uiHover(hx, hy, bw, bh);
    const halted = val(`halt:${b.id}`, !!W.halted);
    rims(hx, hy, bw, bh, hov);
    uiText(txt(B.halt_text[0], B.halt_text[1] + (halted ? 1 : 0)), hx, hy + B.halt_label_y, FONT("11C"), { width: bw, align: "center", wrap: true });
    if (typeof sendCommands === "function") UIX.hits.push([hx, hy, bw, bh, () => {
      const key = `halt:${b.id}`, v = !halted;
      PEND[key] = { v, tick: Infinity };
      Promise.resolve(sendCommands([`halt ${b.x} ${b.y}`], { sound: false })).then(tk => {
        if (tk == null) { if (PEND[key] && PEND[key].v === v) delete PEND[key]; }
        else if (PEND[key] && PEND[key].v === v) PEND[key].tick = tk;
      });
    }, txt(B.halt_text[0], B.halt_text[1] + (halted ? 1 : 0))]);
  }

  // farms and orchard trees 0x00584520: crop icon, "Production is n% complete.", status, workers, text
  PANELS.farm = (b, p, L, T, cols, rows) => {
    const Lf = D.layouts.farm;
    uiPut(icon(b.crop || spec(b).output), L + Lf.icon[0], T + Lf.icon[1]);
    title(b, p, L, T, cols);
    chain(L + 32, T + Lf.line_y, "11C", [txt(p.group, 2), num(b.growth || 0, "@", "%"), txt(p.group, 3)]);
    if (need(b)) {                                // orchard trees have no staff of their own: no status (ours)
      status(b, p, L, T, cols, rows);
      inset(L, T, cols, p);
      workers(b, L, T + p.workers_y);
    }
    desc(p, L, T, cols, rows);
  };

  // industry 0x00582920: output icon, "Holds n raw" (gatherers) / "Production is n% complete." (workshops)
  PANELS.industry = (b, p, L, T, cols, rows) => {
    const Li = D.layouts.industry, sp = spec(b), out = sp.output;
    if (out && b.key !== "chariot_workshop") uiPut(icon(out), L + Li.icon[0], T + Li.icon[1]);
    title(b, p, L, T, cols);
    const g = b.goods || {};
    let inputMissing = false;
    if (sp.kind === "workshop") {
      chain(L + 32, T + Li.line_y, "11C", [txt(p.group, 2), num(I(b).progress || 0, "@", "%"), txt(p.group, 3)]);
      const inp = sp.input, loads = Math.floor((g[inp] || 0) / 100);
      chain(L + 32, T + Li.input_y, "11C", [txt(p.group, 12), ...countNoun(Math.max(0, loads), 8, 10)]);
      inputMissing = (g[inp] || 0) < (sp.batch || 100) && (b.employees || 0) > 0;
    } else {
      const raw = sp.kind === "ranch" ? (g.wheat || 0) : (g[out] || 0);
      chain(L + 32, T + Li.line_y, "11C", [txt(p.group, 2), num(raw, "@", " "), txt(p.group, 3)]);
    }
    const key = staffKey(b, p.ladder);
    if (inputMissing && /^s/.test(key)) para(txt(p.group, 11), L + 32, T + p.status_y_input, (cols - 4) * 16);
    else status(b, p, L, T, cols, rows, key);
    inset(L, T, cols, p);
    workers(b, L, T + p.workers_y);
    desc(p, L, T, cols, rows);
  };

  // trireme wharf 0x00583C60 (sim: navy.wharf_window -> info.wharf). Paragraphs advance the pen y (DAT_00F13A6C)
  // by 16 a line; the top line at +0x2d, then wood / armor, the staffing status, the trireme line, all from
  // +0x37 + pen. Without a trireme: the button (table 0x00642B38, RIMS 384x20 at (L+0x28, T+(H-2)*16), drawn by
  // info_window_draw 0x005724E0, hover variant when hovered), its label 175:19 "Staff" when the crew is home (C4
  // bit 1, ours misc "off") else 175:20 "Send home"; the click (0x00572490) flips the bit = `staff X Y on|off`.
  PANELS.wharf = (b, p, L, T, cols, rows) => {
    const Z = D.layouts.wharf, g = p.group, W = I(b).wharf || {}, X = L + Z.x, goods = b.goods || {};
    const lines = (s, w) => 16 * ZText.wrap(FONT("11C"), s, w).length;
    title(b, p, L, T, cols);
    let pen = 0;
    if (W.palace === false) { para(txt(g, Z.no_palace), X, T + Z.top_y, cols * 16); pen += lines(txt(g, Z.no_palace), cols * 16); }
    else if (W.status === "build" && W.crew_all) {      // "Production is n% complete." (two paragraphs + number)
      const a = txt(g, Z.production[0]), n = num(W.progress || 0, "@", "%");
      line(a, X, T + Z.top_y);
      const px = cursor("11C", a);
      line(n, X + px, T + Z.num_y);
      line(txt(g, Z.production[1]), X + px + cursor("11C", n), T + Z.top_y);
      pen += 32;
    } else if (W.status === "repair") { para(txt(g, Z.repairing), X, T + Z.top_y, cols * 16); pen += lines(txt(g, Z.repairing), cols * 16); }
    const y0 = T + Z.base_y + pen;                      // stored wood (L+0x20) and armor (L+0xe1), loads = /100
    const stock = (k, x, s) => chain(x, y0, "11C", [s, ...countNoun(Math.max(0, Math.floor((goods[k] || 0) / 100)), Z.noun[0], Z.noun[1])]);
    stock("wood", X, txt(g, Z.wood));
    stock("armor", L + Z.armor_x, txt(g, Z.armor));
    pen += Z.gap + lines(txt(g, Z.wood), cols * 16);
    const sy = T + Z.base_y + pen;                      // status (0x00583C60 ladder; crew home 175:4 before "none")
    const [s] = ladderText(b, p, staffKey(b, p.ladder));
    para(s, X, sy, (cols - 4) * 16);
    pen += Z.gap + lines(s, (cols - 4) * 16);
    const t = !W.trireme ? (W.status === "build" ? null : Z.needs) : W.at_wharf ? Z.at_wharf : null;
    if (t != null) para(txt(g, t), X, T + Z.base_y + pen, (cols - 4) * 16);
    inset(L, T, cols, p);
    workers(b, L, T + p.workers_y);
    desc(p, L, T, cols, rows);
    if (W.trireme === false) {
      const [bx, by, bw, bh] = Z.button, x = L + bx, y = T + rows * 16 + by;
      const key = `wharf:${b.id}`, off = val(key, !!I(b).off);
      rims(x, y, bw, bh, uiHover(x, y, bw, bh));
      const label = txt(g, off ? Z.staff : Z.send_home);
      center(label, x, T + rows * 16 + Z.label_dy, bw, "11C");
      if (typeof sendCommands === "function") UIX.hits.push([x, y, bw, bh, () => {
        const v = !off;
        PEND[key] = { v, tick: Infinity };
        Promise.resolve(sendCommands([`staff ${b.x} ${b.y} ${v ? "off" : "on"}`], { sound: false })).then(tk => {
          if (tk == null) { if (PEND[key] && PEND[key].v === v) delete PEND[key]; }
          else if (PEND[key] && PEND[key].v === v) PEND[key].tick = tk;
        });
      }, label]);
    }
  };

  // tower 0x0057A3E0 (sim: defences.tower_window -> info.tower): one status paragraph at +0x2d in the exe's order:
  // fire 170:5, towers ordered unmanned 170:10, no road 69:4, no labour 69:5, no palace 170:8, not on the palace's
  // road network 170:9, no workers 170:2, then 170:3 with a wall sentry (+0x2A) else 170:4; inset +0x97, workers
  // +0x9d. (The Poseidon orichalc lines and a "." at +0xdc drawn with a non-font argument are left out.)
  PANELS.tower = (b, p, L, T, cols, rows) => {
    title(b, p, L, T, cols);
    const Tw = I(b).tower || {}, Ld = p.ladder;
    const k = b.burning ? Ld.fire : Tw.unmanned ? Ld.unmanned : noRoad(b) ? [69, 4] : noLabor(b) ? [69, 5]
      : Tw.palace === false ? Ld.no_palace : Tw.network === false ? Ld.no_network : (b.employees || 0) < 1 ? Ld.none
      : Tw.sentry ? Ld.out : Ld.idle;
    para(ref(k, p.group), L + 32, T + p.status_y, (cols - 4) * 16);
    inset(L, T, cols, p);
    workers(b, L, T + p.workers_y);
  };

  // growers' lodges 0x0057DB80 / 0x0057E2B0: stored fruit lines, status at +0x8f, workers, text
  PANELS.lodge = (b, p, L, T, cols, rows) => {
    title(b, p, L, T, cols);
    const g = b.goods || {}, trees = spec(b).trees || [];
    const goods = trees.map(t => (Build.cat[t] || {}).output);
    (p.stored || []).forEach(([y, , k], i) => {
      const n = Math.floor((g[goods[i]] || 0) / 100);
      chain(L + 32, T + y, "11C", [txt(p.group, k), ...countNoun(Math.max(0, n), 8, 10)]);
    });
    const key = staffKey(b, p.ladder);              // staffing at +0x4c, the growers' state at +0x8f (0x0057DB80)
    const [s] = ladderText(b, p, key);
    para(s, L + 32, T + p.status_y, (cols - 4) * 16);
    if (/^s/.test(key) && I(b).out) para(ref(p.ladder.out, p.group), L + 32, T + p.out_y, (cols - 4) * 16);
    inset(L, T, cols, p);
    workers(b, L, T + p.workers_y);
    if (p.desc_y != null) para(txt(p.group, p.desc_index || 1), L + 32, yOf(T, rows, p.desc_y), (cols - 4) * 16);
  };

  // hunting lodge, corral, fishery, urchin quay: stored line / progress, walker state, workers
  PANELS.gatherer = (b, p, L, T, cols, rows) => {
    title(b, p, L, T, cols);
    const g = b.goods || {}, out = spec(b).output;
    if (p.progress) chain(L + 32, T + p.progress[0], "11C", [txt(p.group, p.progress[1]), num(b.growth || 0, "@", "%"), txt(p.group, p.progress[2])]);
    if (p.stored) chain(L + p.stored[2], T + p.stored[0], "11C",
                        [txt(p.group, p.stored[1]), ...countNoun(Math.floor((g[out] || 0) / 100), 8, 10)]);
    let key = staffKey(b, p.ladder);
    if (/^s/.test(key) && p.ladder.out != null && I(b).out) key = "out";
    else if (/^s/.test(key) && p.ladder.idle != null && !I(b).out) key = "idle";
    const [s] = ladderText(b, p, key);
    para(s, L + 32, T + p.status_y, (cols - 4) * 16);
    inset(L, T, cols, p);
    workers(b, L, T + p.workers_y);
    desc(p, L, T, cols, rows);
  };

  // houses 0x0057F4E0 (+ 0x00576DA0 occupants, 0x00576F60 tax, 0x00577060 unrest); empty lot 0x0057FF00
  PANELS.house = (b, p, L, T, cols, rows) => {
    const H = D.layouts.house, info = I(b), elite = b.level >= 7;
    if (!elite && !b.occupants) {
      const E = H.empty;
      center(ref(E.title), L, T + E.title_y, cols * 16, "22C");
      uiFrame("plain", L + 16, T + E.list_inset[0], cols - 2, E.list_inset[1]);
      center(ref(E.nobody), L, T + E.nobody_y, cols * 16, "11CB");
      para(ref(noRoad(b) ? E.no_road : E.ok), L + 32, T + rows * 16 + E.text_dy, (cols - 4) * 16);
      return;
    }
    center(txt(H.title_group, b.level), L, T + 10, cols * 16, "22C");
    uiFrame("plain", L + 16, T + H.inset[0], cols - 2, H.inset[1]);
    // occupants: icon, " n occupants", "n too many" / "Extra room for n"
    const O = H.occupants;
    uiPut(sprite(D.icons.occupants.file, D.icons.occupants.index), L + O.icon[0], T + O.icon[1]);
    const room = info.room != null ? info.room : (b.capacity || 0) - (b.occupants || 0);
    chain(L + O.text[0], T + O.text[1], O.font, [num(b.occupants || 0), txt(127, 15),
      ...(room < 0 ? [num(-room), txt(127, 16)] : room > 0 ? [txt(127, 17), num(room)] : [])]);
    // tax
    const X = H.tax;
    if (info.taxed === undefined) { /* old server: no tax data */ }
    else if (!info.taxed) line(txt(127, 18), L + X.x, T + X.y, X.font);
    else chain(L + X.x, T + X.y, X.font, [txt(127, 19), ...countNoun(info.tax_month || 0, 8, 0), txt(127, 20)]);
    // unrest
    const U = H.unrest;
    if (info.unrest != null) line(txt(127, U.steps.find(s => info.unrest < s[0])[1]), L + U.x, T + U.y, U.font);
    if (!elite && (info.food_types === 0 || b.level === 0)) para(ref(H.forage.ref), L + H.forage.x, T + H.forage.y, (cols - 6) * 16, H.forage.font);
    // food and goods row
    const g = b.goods || {};
    const food = info.food != null ? info.food : D.foods.reduce((a, f) => a + (g[f] || 0), 0);
    uiPut(icon("food"), L + H.food.icon[0], T + H.food.icon[1]);
    line(num(food), L + H.food.num[0], T + H.food.num[1], H.food.font);
    (elite ? H.goods.elite : H.goods.common).forEach((good, i) => {
      const [sx, sy] = H.goods.slots[i];
      uiPut(icon(good), L + sx, T + sy);
      line(num(g[good] || 0), L + sx + H.goods.num_dx, T + sy, H.food.font);
    });
    // status: fire, no road, else evolve text 127:(36 + code)
    const S = H.status;
    let s;
    if (b.burning) s = ref(S.fire);
    else if (noRoad(b)) s = ref(S.no_road);
    else if (info.code != null) s = txt(S.base[0], S.base[1] + info.code);
    else s = b.reason || "";                                       // old server: our own reason string
    para(s, L + S.x, T + S.y, (cols - 4) * 16, S.font);
  };

  // granary / storehouse 0x005B2880 + rows 0x005B38C0 (window at its own size)
  // orders/limits the player picked show at once and are kept until the tab has the snapshot the server
  // recorded after applying them (S.seq; the pages.js PEND pattern)
  const PEND = {};
  // have: the snapshot seq the data shown was read at (default S.seq; the trade window: its /trade_post.json's, which
  // is fetched only after S reaches the new seq, so dropping at S.seq showed the old limit for that fetch: bug 440)
  function val(key, actual, have) {
    const p = PEND[key];
    if (have === undefined) have = typeof S === "undefined" || !S ? null : S.seq;
    if (p && (have == null || have < p.tick)) return p.v;
    delete PEND[key];
    return actual;
  }
  const CYCLE = { accept: "get", get: "empty", empty: "refuse", refuse: "accept" };   // 0x005B1670 (orders 0,2,3,1)
  function limitStep(k, lim, down) {               // 0x005B14B0: 100 below 1200, 400 above (sculpture always 400)
    if (k === "sculpture" || lim > 1200) return 400;
    return lim < 1200 || down ? 100 : 400;
  }
  // storage X Y GOOD ORDER [LIMIT] (sim/game.py); goods: one key or a list (the X button)
  function setStore(b, goods, ord, lim) {
    const list = Array.isArray(goods) ? goods : [goods];
    const os = list.map((k, j) => Array.isArray(ord) ? ord[j] : ord);          // ord: one order or one per good
    const cmds = list.map((k, j) => `storage ${b.x} ${b.y} ${k} ${os[j]}` + (lim != null ? ` ${lim}` : ""));
    const keys = list.map((k, j) => [`ord:${b.id}:${k}`, os[j]]).concat(lim != null ? list.map(k => [`lim:${b.id}:${k}`, lim]) : []);
    for (const [key, v] of keys) PEND[key] = { v, tick: Infinity };
    Promise.resolve(sendCommands(cmds, { sound: false })).then(t => {
      for (const [key, v] of keys) {
        if (t == null) { if (PEND[key] && PEND[key].v === v) delete PEND[key]; }
        else if (PEND[key] && PEND[key].v === v) PEND[key].tick = t;
      }
    });
  }
  function storageGoods(b) {
    const sp = spec(b), food = sp.accepts === "food";
    // the city's goods list (sim/export.py goods_list: rebuild_goods_lists 0x005BAAF0 in an episode or the
    // original's open plays; ours, sandbox_open: every good a building produces), plus what the building holds
    const list = [...new Set([...((typeof S !== "undefined" && S && S.goods_list) || []), ...Object.keys(b.goods || {})])];
    const isFood = k => D.foods.includes(k);
    const res = D.resource_ids;
    return list.filter(k => res[k] != null && res[k] <= 22 && (food ? isFood(k) : (!isFood(k) || k === "wheat") && k !== "horses" && k !== "chariot"))
      .sort((a, c) => res[a] - res[c]);
  }
  PANELS.storage = (b, p, L, T, cols, rows) => {
    const Z = D.layouts.storage, info = I(b), g = b.goods || {}, sp = spec(b);
    center(p.title || txt(28, p.zeus_id) || sp.name, L, T + Z.title_y, cols * 16, "22C");
    // status (0x005B2420): one paragraph, 20 px
    const [st] = ladderText(b, Object.assign({}, p, { ladder: D.panels.road.ladder }), staffKey(b, {}));
    para(st, L + 32, T + Z.status_y, (cols - 4) * 16);
    const local = Z.status_h;
    const rule = y => UIX.black && uiPut(UIX.black, L + 16, y, 1, cols * 16 - 31, 1);   // 0x00509700: x1..x2 inclusive
    const held = Object.values(g).reduce((a, v) => a + v, 0), cap = sp.capacity || 3200;
    const base = local + Z.storing.base;
    if (sp.accepts !== "food") {
      chain(L + Z.storing.x, T + base, "11C", [txt(130, 5), ...countNoun(Math.floor(held / 100), 8, 16)]);
      chain(L + Z.storing.space_x, T + base, "11C", [txt(130, 6), ...countNoun(Math.floor((cap - held) / 100), 8, 16)]);
    } else if (cap - held < 100) center(ref(Z.full.ref), L + 16, T + base, (cols - 2) * 16, "11C");
    rule(T + base + Z.storing.rule_dy);
    const hb = local + Z.header.base;
    rule(T + hb + Z.header.rule_dy);
    rule(T + hb + Z.header.rule2_dy);
    for (const [x, k] of Z.header.cols) line(txt(130, k), L + x, T + hb + Z.header.dy, Z.header.font);
    const R = Z.rows, orders = info.orders || {}, limits = info.limits || {};
    const live = !sp.endless && typeof sendCommands === "function";      // the endless test sink takes no orders
    const goods = storageGoods(b);
    goods.forEach((k, i) => {
      const y = T + R.first + local + R.step * i, n = g[k] || 0, unit = k === "sculpture" ? 400 : 100;   // 0x005B3660
      const ord = val(`ord:${b.id}:${k}`, orders[k] || (sp.accepts !== "food" && D.foods.includes(k) ? "refuse" : "accept"));   // storehouse wheat starts refused (0x00494960)
      const lim = val(`lim:${b.id}:${k}`, limits[k] != null ? limits[k] : cap);
      // fonts (0x005B3660 / 0x005B38C0): stock number and name 11LTYEL when the good can't be taken in
      // (0x005B3540: stock >= limit, or every bay holds something and this good fills whole bays), else 11C when
      // none stored, else 11LTBLUE; the order's own font does not enter it. The sim has no bays: bays in use =
      // sum of ceil(amount / 400) over goods (approximation).
      const bays = Object.values(g).reduce((a, v) => a + Math.ceil(v / 400), 0);
      const accepting = !(n >= lim || (n % 400 === 0 && bays >= Math.floor(cap / 400)));
      const f = !accepting ? R.fonts.full : n === 0 ? R.fonts.empty : R.fonts.stock;
      if (n) uiPut(icon(k), L + R.icon_x, y + R.icon_dy);
      line(num(Math.floor(n / unit)), L + R.num_x, y, f);
      line(txt(23, D.resource_ids[k]), L + R.name_x, y, f);
      const [oi, of] = R.orders[ord] || R.orders.accept;
      // order button 0x0065B330: 110x20 at (L+291, y-3); RIMS only while hovered; click 0x005B1670 cycles
      // accept -> get -> empty -> don't accept -> accept
      const bx = L + 291, by = y - 3;
      if (live && uiHover(bx, by, 110, 20)) rims(bx, by, 110, 20, true);
      line(txt(130, oi), L + R.order_x, y + 1, of);
      line(num(Math.floor(lim / unit)), L + R.limit_x, y, accepting ? of : R.fonts.full);   // the order's font, 11LTYEL when not accepting (0x005B38C0)
      if (!live) return;
      const next = CYCLE[ord] || "get";
      UIX.hits.push([bx, by, 110, 20, () => setStore(b, k, next, null), txt(130, oi)]);
      // stock limit arrows 0x01607560 (built by 0x005B1B20): 17x17 at (L+425, y-2), down then up at +17;
      // click 0x005B1500: step 0x005B14B0, clamped to 0..capacity
      [[0, "SPR_SM_BUTTON_DOWN", 1], [17, "SPR_SM_BUTTON_UP", 0]].forEach(([dx, grp, down]) => {
        const ax = L + 425 + dx, ay = y - 2, hov = uiHover(ax, ay, 17, 17);
        uiPut(groupSprite("Zeus_Interface", grp, hov ? 1 : 0), ax, ay);
        const nl = down ? Math.max(0, lim - limitStep(k, lim, true)) : Math.min(cap, lim + limitStep(k, lim, false));
        UIX.hits.push([ax, ay, 17, 17, () => nl !== lim && setStore(b, k, ord, nl), down ? "Lower stock limit" : "Raise stock limit", true]);
      });
    });
    // "All goods" row (ours, a deviation the user asked for 10-28; the exe has none): one order button and one pair
    // of limit arrows that set every listed good at once (one `storage` command per good, one batch). Shows the
    // common order / limit, or "-" when the goods differ; a click cycles from the common order (accept if mixed)
    // and steps from the common limit (the highest when mixed).
    if (live && goods.length) {
      const y = T + R.first + local + R.step * goods.length;
      const ords = goods.map(k => val(`ord:${b.id}:${k}`, orders[k] || (sp.accepts !== "food" && D.foods.includes(k) ? "refuse" : "accept")));
      const lims = goods.map(k => val(`lim:${b.id}:${k}`, limits[k] != null ? limits[k] : cap));
      const same = ords.every(o => o === ords[0]), ord = same ? ords[0] : null;
      const lsame = lims.every(v => v === lims[0]), lim = lsame ? lims[0] : Math.max(...lims);
      line("All goods", L + R.name_x, y, R.fonts.empty);
      const [oi, of] = (ord && R.orders[ord]) || R.orders.accept;
      const bx = L + 291, by = y - 3;
      if (uiHover(bx, by, 110, 20)) rims(bx, by, 110, 20, true);
      line(ord ? txt(130, oi) : "-", L + R.order_x, y + 1, ord ? of : R.fonts.empty);
      line(lsame ? num(Math.floor(lim / 100)) : "-", L + R.limit_x, y, ord ? of : R.fonts.empty);
      UIX.hits.push([bx, by, 110, 20, () => setStore(b, goods, CYCLE[ord || "refuse"], null), "Order for all goods"]);
      [[0, "SPR_SM_BUTTON_DOWN", 1], [17, "SPR_SM_BUTTON_UP", 0]].forEach(([dx, grp, down]) => {
        const ax = L + 425 + dx, ay = y - 2, hov = uiHover(ax, ay, 17, 17);
        uiPut(groupSprite("Zeus_Interface", grp, hov ? 1 : 0), ax, ay);
        const nl = down ? Math.max(0, lim - limitStep("", lim, true)) : Math.min(cap, lim + limitStep("", lim, false));
        // each good keeps its own order; the limit is the same for all
        UIX.hits.push([ax, ay, 17, 17, () => { if (nl !== lim || !lsame) setStore(b, goods, ords, nl); },
                       down ? "Lower the stock limit of all goods" : "Raise the stock limit of all goods", true]);
      });
    }
    // "X" button 0x0065B310 (20x20 at (L+(C-2)*16, T+(R-5)*16)), 130:11 centred at T+R*16-76; click 0x005B1C90:
    // every good "Don't Accept"
    if (live) {
      const xx = L + (cols - 2) * 16, xy = T + (rows - 5) * 16;
      rims(xx, xy, 20, 20, uiHover(xx, xy, 20, 20));
      center(txt(130, 11), xx, T + rows * 16 - 76, 20, "11C");
      UIX.hits.push([xx, xy, 20, 20, () => setStore(b, goods, "refuse", null), "Don't accept any goods"]);
    }
    // workers box (0x005B1DE0) and the deliverymen line
    const W = Z.workers, wy = T + rows * 16 - 16 * W.inset_rows_from_bottom;
    uiFrame("plain", L + W.inset_x, wy, cols - W.cols_less, 5);
    const n = need(b), e = b.employees || 0;
    uiPut(sprite(D.icons.workers.file, D.icons.workers.index), L + W.inset_x + W.icon_dx, wy + 6);
    chain(L + W.inset_x + W.text_dx, wy + W.dy, W.font, [...countNoun(e, 8, 12), num(n, "(", " "), txt(69, 0)]);
    if (e < n) para(txt(69, pop() > 0 ? 3 : 1), L + W.inset_x + W.text_dx, wy + W.reason_dy, 400, W.font);
    const out = I(b).out;
    para(txt(130, sp.accepts === "food" ? (out ? 31 : 33) : (out ? 27 : 30)), L + Z.deliverymen.x,
         T + rows * 16 + Z.deliverymen.dy, (cols - 5) * 16, Z.deliverymen.font);
  };

  // trading post / dock (bugs.md 117): window 0x005B2880 (trade branch) + rows 0x005B38C0, 32 x 25 cells
  // (info_window_open 0x005715A0). Title "%s (%s)" (28:type, the partner city) in 11C at T+15; status at
  // (L+32, T+36); "Storing n loads" / "Space for n" at L+34 / L+312; headers in 9LTBK: 130:8 Stock (L+23),
  // 130:14 Price (L+192), 130:15 Limit (L+358), 130:16 "Traded so far this year" (L+407, width 100).
  // Imports (what the partner sells; 130:17 in 11LTBLUE, 130:19 "None") then exports (what it buys;
  // 130:18), one row per good every 20 px from Y0 = T+112+20 (status height): stock and name as a
  // storage row (0x005B3660), price at L+196 with the coin at (L+182, y-6), a 103x20 toggle at (L+242, y-4)
  // with 130:12 Buying / 130:20 Not Buying (exports 130:13 Selling / 130:21 Not Selling) centred, 11LTBLUE
  // when on, the limit /100 at L+343, its arrows (0x005B1500, steps 0x005B14B0, 0..6000) at (L+373, y-5),
  // and "used of quota" at L+427. Data: sim/live.py /trade_post.json; clicks send `trade X Y GOOD ...`.
  const TP = {};                                   // building id -> {seq, d} (last /trade_post.json)
  function tradeData(b) {
    const t = TP[b.id], seq = (typeof P !== "undefined" && P.stateSeq) || 0;
    if ((!t || t.seq !== seq) && !(t && t.busy)) {
      TP[b.id] = Object.assign(t || {}, { busy: true });
      getJSON(`/trade_post.json?id=${b.id}`).then(d => { TP[b.id] = { seq, d }; }).catch(() => { TP[b.id].busy = false; });
    }
    return t && t.d;
  }
  function setTrade(b, k, mode, lim) {             // trade X Y GOOD import|export|off [LIMIT] (sim/game.py)
    const keys = [[`tord:${b.id}:${k}`, mode]].concat(lim != null ? [[`tlim:${b.id}:${k}`, lim]] : []);
    for (const [key, v] of keys) PEND[key] = { v, tick: Infinity };
    Promise.resolve(sendCommands([`trade ${b.x} ${b.y} ${k} ${mode}` + (lim != null ? ` ${lim}` : "")], { sound: false })).then(t => {
      for (const [key, v] of keys) {
        if (t == null) { if (PEND[key] && PEND[key].v === v) delete PEND[key]; }
        else if (PEND[key] && PEND[key].v === v) PEND[key].tick = t;
      }
    });
  }
  // next / previous trade building (bugs.md 20): image table 0x0065B800 drawn by 0x005B2880 while trading posts +
  // docks (0x00782CF0 + 0x00782CF4) > 1: SPR_BUTTON_LEFT at (L+0x1BE, T+9) (arg 1: previous), SPR_BUTTON_RIGHT at
  // +24 (arg 0: next), 24 x 24, type 4: the pressed picture (+1) while held, no hover look; fires on the press and
  // repeats while held (FUN_00431C80, table 0x005F0028: oracle 1F-trade3 L1 stepped twice). Click 0x005B1CE0: the
  // next / previous dock or post after this one in storage record order (index 1..199, wrapping), whose window it
  // opens (0x00570B20, 0x005715A0) and centres the view on (0x0044A7D0). Ours: storage records are taken in build
  // order, so building id order (a record freed by a demolition and taken again breaks that: not seen).
  function tradeCycle(b, L, T) {
    const all = ((typeof S !== "undefined" && S.buildings) || []).filter(o => o.kind === "trade").sort((a, c) => a.id - c.id);
    if (all.length < 2) return;
    [[0, "SPR_BUTTON_LEFT", -1], [24, "SPR_BUTTON_RIGHT", 1]].forEach(([dx, grp, step]) => {
      const x = L + 0x1BE + dx, y = T + 9, held = uiHover(x, y, 24, 24) && UIX.down;
      uiPut(groupSprite("Zeus_Interface", grp, held ? 1 : 0), x, y);
      UIX.hits.push([x, y, 24, 24, () => {
        const i = all.findIndex(o => o.id === b.id), o = all[(i + step + all.length) % all.length];
        if (!o || o.id === b.id) return;
        cam.x = tileX(o.x, o.y) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
        cam.y = tileY(o.x, o.y) - innerHeight / 2 / cam.zoom;
        openInfo(o, UIX.info ? UIX.info.mx : innerWidth / 2, UIX.info ? UIX.info.my : innerHeight / 2);
      }, step < 0 ? "previous" : "next", true]);     // held: repeats as every image button (FUN_00431C80, ui.js)
    });
  }
  PANELS.trade = (b, p, L, T, cols, rows) => {
    const Z = D.layouts.storage, d = tradeData(b) || {}, sp = spec(b), g = b.goods || {};
    const dSeq = TP[b.id] && TP[b.id].d ? TP[b.id].seq : null;           // the snapshot seq d was asked at (val)
    const tname = txt(28, p.zeus_id) || sp.name;
    center(d.partner ? `${tname}: ${d.partner}` : tname, L, T + 15, cols * 16, "11C");   // "%s: %s" 0x0065B838
    tradeCycle(b, L, T);
    const [st] = ladderText(b, Object.assign({}, p, { ladder: D.panels.road.ladder }), staffKey(b, {}));
    para(st, L + 32, T + Z.status_y, (cols - 4) * 16);
    const local = Z.status_h, rule = y => UIX.black && uiPut(UIX.black, L + 16, y, 1, cols * 16 - 31, 1);   // 0x00509700: to L+cols*16-16 inclusive
    const cap = d.capacity || sp.capacity || 6000, held = Object.values(g).reduce((a, v) => a + v, 0);
    const base = local + 0x26;
    rule(T + base - 5);
    chain(L + 0x22, T + base, "11C", [txt(130, 5), ...countNoun(Math.floor(held / 100), 8, 16)]);
    chain(L + 0x138, T + base, "11C", [txt(130, 6), ...countNoun(Math.floor((cap - held) / 100), 8, 16)]);
    rule(T + base + 15);
    for (const [x, k] of [[0x17, 8], [0xc0, 14], [0x166, 15]]) line(txt(130, k), L + x, T + base + 0x1f, "9LTBK");
    para(txt(130, 16), L + 0x197, T + base + 0x14, 100, "9LTBK");
    rule(T + base + 0x2b);
    if (!d.partner) return;
    const res = D.resource_ids, byId = (a, c) => res[a] - res[c];
    // storage_goods_list 0x005B12C0 (0x3D / 0x3E): the city's goods list entries the partner sells / buys
    const GL = (typeof S !== "undefined" && S && S.goods_list) || null, inList = k => !GL || GL.includes(k);
    const imports = Object.keys(d.sells || {}).filter(k => res[k] != null && inList(k)).sort(byId);
    const exports = Object.keys(d.buys || {}).filter(k => res[k] != null && inList(k)).sort(byId);
    const live = typeof sendCommands === "function", R = Z.rows, Y0 = T + 0x70 + local;
    const cost = UIX.D.submenu.cost.icon;
    // the window is tall enough for every row (size(): bugs.md 138), so nothing lies under the workers box
    const under = () => false;
    const rowsOf = (list, y0, on, onTxt, offTxt, quota) => list.forEach((k, i) => {
      const y = y0 + 20 * i, n = g[k] || 0, unit = (d.units || {})[k] || 100;
      if (under(y)) return;
      const mode = val(`tord:${b.id}:${k}`, (d.orders || {})[k] || "off", dSeq), active = mode === on;
      const lim = val(`tlim:${b.id}:${k}`, (d.limits || {})[k] != null ? d.limits[k] : cap, dSeq);
      const accepting = !(n >= lim || held + unit > cap);            // 0x005B3540 (no bays here: ours)
      const f = !accepting ? R.fonts.full : n === 0 ? R.fonts.empty : R.fonts.stock;
      if (n) uiPut(icon(k), L + R.icon_x, y + R.icon_dy);
      line(num(Math.floor(n / unit)), L + R.num_x, y, f);
      line(txt(23, res[k]), L + R.name_x, y, f);
      line(num((d.prices || {})[k] || 0), L + 0xc4, y, "11C");
      uiPut(sprite(cost.file, cost.index), L + 0xb6, y - 6);
      const bx = L + 0xf2, by = y - 4, hov = live && uiHover(bx, by, 103, 20);
      rims(bx, by, 103, 20, hov);                    // 0x00509230 for every row, hover variant on the hovered one
      center(txt(130, active ? onTxt : offTxt), bx, y + 2, 103, active ? "11LTBLUE" : "11C");
      line(num(Math.floor(lim / unit)), L + 0x157, y, !accepting ? R.fonts.full : active ? "11LTBLUE" : "11C");
      line(`${((d.used || {})[k]) || 0} ${txt(44, 148)} ${quota[k] || 0}`, L + 0x1ab, y, "11C");
      if (!live) return;
      UIX.hits.push([bx, by, 103, 20, () => setTrade(b, k, active ? "off" : on, null), txt(130, active ? onTxt : offTxt)]);
      [[0, "SPR_SM_BUTTON_DOWN", 1], [17, "SPR_SM_BUTTON_UP", 0]].forEach(([dx, grp, down]) => {
        const ax = L + 0x175 + dx, ay = y - 5, h2 = uiHover(ax, ay, 17, 17);
        uiPut(groupSprite("Zeus_Interface", grp, h2 ? 1 : 0), ax, ay);
        const nl = down ? Math.max(0, lim - limitStep(k, lim, true)) : Math.min(cap, lim + limitStep(k, lim, false));
        UIX.hits.push([ax, ay, 17, 17, () => nl !== lim && setTrade(b, k, mode, nl), down ? "Lower the limit" : "Raise the limit", true]);
      });
    });
    line(txt(130, 17), L + 0x20, Y0 - 0x1a, "11LTBLUE");
    if (!imports.length) line(txt(130, 19), L + 0x20, Y0 - 0xb, "11C");
    rowsOf(imports, Y0, "import", 12, 20, d.sells);
    rule(Y0 + 6 + imports.length * 20);
    const E0 = Y0 + 20 * imports.length + 40;
    if (!under(E0 - 0x1a)) line(txt(130, 18), L + 0x20, E0 - 0x1a, "11LTBLUE");
    if (!exports.length && !under(Y0 + 0x22 + imports.length * 20)) line(txt(130, 19), L + 0x20, Y0 + 0x22 + imports.length * 20, "11C");
    rowsOf(exports, E0, "export", 13, 21, d.buys);
    // 0x005B38C0: with no exports the count is set to 1 before "None" is drawn, so the closing rule is one row lower
    // (bugs.md 445: it went through "None")
    rule(T + (imports.length + (exports.length || 1)) * 20 + 0x98 + local);
    // workers box (0x005B1DE0), as in the storage window
    const W = Z.workers, wy = T + rows * 16 - 16 * W.inset_rows_from_bottom;
    uiFrame("plain", L + W.inset_x, wy, cols - W.cols_less, 5);
    const nn = need(b), e = b.employees || 0;
    uiPut(sprite(D.icons.workers.file, D.icons.workers.index), L + W.inset_x + W.icon_dx, wy + 6);
    chain(L + W.inset_x + W.text_dx, wy + W.dy, W.font, [...countNoun(e, 8, 12), num(nn, "(", " "), txt(69, 0)]);
    if (e < nn) para(txt(69, pop() > 0 ? 3 : 1), L + W.inset_x + W.text_dx, wy + W.reason_dy, 400, W.font);
    para(txt(130, I(b).out ? 27 : 30), L + Z.deliverymen.x, T + rows * 16 + Z.deliverymen.dy, (cols - 5) * 16,
         Z.deliverymen.font);                        // shared tail of 0x005B2880, as in the storage window (seen)
  };

  // agoras 0x0057AA10 + vendor boxes 0x0040B5F0
  PANELS.agora = (b, p, L, T, cols, rows) => {
    const A = D.layouts.agora, info = I(b), g = b.goods || {};
    center(txt(97, b.key === "grand_agora" ? 1 : 0), L, T + 10, cols * 16, "22C");
    const stalls = info.stalls || [];
    const food = D.foods.reduce((a, f) => a + (g[f] || 0), 0);
    A.vendors.forEach(([vkey, good], i) => {
      const [bx, by, bw, bh] = A.boxes[i], x = L + bx, y = T + by, B = A.box;
      const name = good === "food" ? txt(23, 43) : txt(23, D.resource_ids[good]);
      line(name, x + B.name[0], y + B.name[1], B.name_font);
      uiPut(icon(good), x + B.icon[0], y + B.icon[1]);
      let amt = good === "food" ? food : (g[good] || 0);
      if (good === "armor" || good === "horses") amt = Math.floor(amt / 100);
      line(num(amt), x + B.num[0], y + B.num[1], B.num_font);
      rims(x, y, bw, bh, uiHover(x, y, bw, bh));
      const s = stalls.find(q => q.key === vkey), St = A.states;
      let st;
      if (!s) st = St.no_vendor;
      else if (!s.employees) st = St.no_labor;
      else if (!amt) st = s.buying ? St.buying : /^no storage/.test(s.reason || "") ? [14, "11C"] : St.no_goods;
      else st = info.peddler ? St.distributing : St.no_demand;
      line(txt(97, st[0]), x + B.state[0], y + B.state[1], st[1]);
    });
    uiFrame("plain", L + 16, T + A.inset[0], cols - 2, A.inset[1]);
    const n = stalls.reduce((a, s) => a + (s.need || 0), 0), e = stalls.reduce((a, s) => a + (s.employees || 0), 0);
    workers(b, L, T + A.workers_y, n, e);
    if (pop() === 0) return;
    const Q = A.status, w = (cols - 4) * 16;
    if (b.burning) return para(txt(97, Q.fire[1]), L + 32, T + Q.fire[0], w, Q.font);
    if (!stalls.length || stalls.every(s => s.key === "empty_stall")) return para(txt(97, Q.no_stalls[1]), L + 32, T + Q.no_stalls[0], w, Q.font);
    if (noRoad(b)) return para(txt(69, 4), L + 32, T + Q.no_road[0], w);
    if (!e) return para(txt(97, Q.none[1]), L + 32, T + Q.none[0], w, Q.font);
    if (info.peddler) {          // the exe also draws the peddler's goods icon at Q.icon (blank when it carries none: seen)
      return para(txt(97, info.returning ? Q.back[1] : Q.out[1]), L + Q.text_x, T + Q.out[0], (cols - 6) * 16, Q.font);
    }
    para(txt(97, Q.waiting[1]), L + 32, T + Q.waiting[0], w, Q.font);
  };

  // --- entry points --------------------------------------------------------------------------------
  function target(b) {                              // a stall shows its agora's window (ours: stalls are parts of it)
    const p = panelOf(b);
    if (!p || p.panel !== "agora_part" || typeof S === "undefined" || !S) return b;
    return S.buildings.find(q => q.kind === "agora" && b.x >= q.x - 2 && b.x <= q.x + (q.w || 6)
                                 && b.y >= q.y - 2 && b.y <= q.y + (q.h || 6)) || b;
  }

  function size(b) {
    const p = panelOf(b);
    if (!p) return null;
    if (b.kind === "trade") {                      // 0x005715A0: 0x20 x 0x19, fixed; ours grows (bugs.md 138)
      // the exe draws the rows (FUN_005B38C0, info_window_draw) after the window and its workers box
      // (FUN_005B2880, background), at 20 px steps from T+0x70+status with no cap: from 4 imports + 3 exports on
      // the last rows lie on the box, their text and buttons drawn over it. Ours (deviation, user 10-28): the
      // window is made taller until the last row ends 4 px above the box (box top = T + rows*16 - 96).
      const d = tradeData(b) || {}, res = D.resource_ids;
      const ni = Object.keys(d.sells || {}).filter(k => res[k] != null).length;
      const ne = Object.keys(d.buys || {}).filter(k => res[k] != null).length;
      const last = 0x70 + D.layouts.storage.status_h + 20 * ni + 40 + 20 * Math.max(0, ne - 1);   // last row's y - T
      const rows = Math.max(25, Math.ceil((last + 16 + 4 + 96) / 16));
      return { cols: 32, rows, close_x: 32 * 16 - 36 };
    }
    if (p.panel === "storage") {
      const n = storageGoods(b).length + (spec(b).endless ? 0 : 1);     // + our "All goods" row
      return { cols: D.layouts.storage.cols, rows: Math.ceil((4 * n) / 3) + 13, close_x: D.layouts.storage.close_x };
    }
    return { cols: D.cols, rows: p.rows || 22 };
  }

  function draw(b, L, T, cols, rows) {
    const p = panelOf(b);
    if (!p || !ready()) return false;
    const fn = b.kind === "trade" ? PANELS.trade : PANELS[p.panel] || PANELS.generic;
    fn(b, p, L, T, cols, rows);
    return true;
  }

  // --- walker window: the land window's figure list (0x00573540) and the selected figure (0x005740A0) --
  // Positions are the exe's (L, T = window corner; 29 x 22 cells). Row: up to 7 RIMS boxes 52x52 at
  // (L+25+60i, T+45) in an inset (L+16, T+40, cols-2, 12 rows; 15 for carts 4/9/36); each with a 48x48 crop of
  // the map at the figure's picture, the figure alone (FUN_00572FE0; play.js drawCrop). Selected
  // figure (default branch): RIMS box (L+24, T+102, (cols-3)*16, 122; 167 for carts), portrait
  // SPR_FIG_PORTRAIT + type at (L+28, T+112), name (name group, name index) in 22C2 at (L+90, T+108),
  // 64:type in 11CB at (L+92, T+139), thought (thought group, phrase) in 11CB at (L+90, T+160), width
  // (cols-9)*16. Type-specific lines (cart cargo and origin, peddler's goods, soldiers...) are not drawn.
  // wall (FUN_005776A0, a wall tile's land window): title 166:0, text 166:1 at (L+0x20, T+H*16-0x9E)
  function wallPanel(L, T, cols, rows) {
    center(txt(166, 0), L, T + 10, cols * 16, "22C");
    para(txt(166, 1), L + 0x20, T + rows * 16 - 0x9e, (cols - 4) * 16);
  }
  PANELS.wall = (b, p, L, T, cols, rows) => wallPanel(L, T, cols, rows);
  // rubble (FUN_0057DA10, the land window's kind 8, no walker row): title 140:0 at T+10, the name of the building
  // it came from (28:g_grid_ruin_type, small font) at (L+0x20, T+H*16-0xAD), text 140:1 at (L+0x20, T+H*16-0x8F)
  // (bugs.md 343). Not played: wavs/ruin.wav on opening (land window sounds are not ported).
  function rubblePanel(key, L, T, cols, rows) {
    center(txt(140, 0), L, T + 10, cols * 16, "22C");
    const p = key && D.panels[key], name = p && p.zeus_id != null ? txt(28, p.zeus_id) : "";
    if (name) para(name, L + 0x20, T + rows * 16 - 0xad, (cols - 4) * 16);
    para(txt(140, 1), L + 0x20, T + rows * 16 - 0x8f, (cols - 4) * 16);
  }

  function drawWalkers(I, L, T, cols, rows) {
    const WI = MAP.walker_info, data = I.data || [];
    if (!WI || !ready()) return;
    const wt = (g, i) => (WI.texts[String(g)] || [])[i] || "";
    if (I.land === 0x18) return wallPanel(L, T, cols, rows);
    if (I.land === 8) return rubblePanel(I.ruin, L, T, cols, rows);
    const sel = data.find(d => d.id === I.ids[I.sel]) || data[0];
    const cart = sel && [4, 9, 36].includes(sel.type);
    uiFrame("plain", L + 16, T + 0x28, cols - 2, cart ? 15 : 12);
    const hits = Scene.walkerHits();
    // land window (FUN_005731D0): with nobody, the title 70:(k+10) and 70:0 in the inset (FUN_00573540); the
    // land's text 70:(k+41) at (L+0x24, T+H*16-0x71) except kinds 0, 6 (road), 0xD; kind 0x18 is the wall panel
    const k = I.land;
    if (k != null && !I.ids.length) center(txt(70, k + 10), L, T + 10, cols * 16, "22C");
    if (!I.ids.length) center(txt(70, 0), L, T + 0x78, cols * 16, "11CB");
    if (k != null && k !== 0 && k !== 6 && k !== 0xd) para(txt(70, k + 41), L + 0x24, T + rows * 16 - 0x71, (cols - 4) * 16);
    I.ids.forEach((id, i) => {
      const bx = L + 0x19 + 60 * i, by = T + 0x2d, on = i === I.sel;
      rims(bx, by, 52, 52, on);
      const h = hits.find(q => q[0] === id);
      if (h) (I.look || (I.look = {}))[id] = [h[8], h[9]];         // gone from view: its last picture
      const lk = I.look && I.look[id], sp = lk && sprite(lk[0], lk[1]);
      if (typeof drawCrop === "function" && drawCrop(id, bx + 2, by + 2, 48, 48)) { /* the map around it (play.js) */ }
      else if (sp) {                                              // no scene yet: its picture scaled into the box
        const k = Math.min(1, 48 / sp.w, 48 / sp.h), w = Math.round(sp.w * k), hh = Math.round(sp.h * k);
        uiPut(sp, bx + 2 + ((48 - w) >> 1), by + 2 + 48 - hh, 1, w, hh);
      }
      UIX.hits.push([bx, by, 52, 52, () => {                     // 0x00405E90: select, then the voice (FUN_005ABD00)
        I.sel = i;
        if (typeof audio !== "undefined" && audio) audio.walkerVoice(data.find(d => d.id === id));
      }, ""]);
    });
    if (!sel) return;
    drawFigure(sel, L, T, cols, rows, cart, wt, WI);
  }

  // gods / monsters / heroes (cases 0x43 / 0x44 / 0x45): portrait (FUN_00573880 by id: SPR_GOD / MONSTER / HERO
  // _PORTRAITS, Poseidon's from Poseidon_Unloaded) at (L+28, T+112); name 157 / 190 / 185:id in 22C2 at (L+90,
  // T+108); a god: 158:id (title) at T+0x8a, 83:unfriendly at T+0x9e, its phrase at T+0xb2 width 0x15a; a hero:
  // 64:69 at T+0x8b; monster and hero phrases at T+0xa0 width (cols-9)*16, all 11CB (docs/play/info.md "Gods,
  // monsters and heroes").
  // the selected figure (0x005740A0): RIMS box (L+24, T+102, (cols-3)*16, 122; 167 for carts 4/9/36), portrait
  // (FUN_00573880) at (L+28, T+112), name (22C2) at (L+90, T+108), 64:type (11CB) at (L+92, T+139), thought
  // paragraph (11CB) at (L+90, T+160) width (cols-9)*16; per type its own lines (spec: docs/play/info.md
  // "Walker window"). Pieces "at pen" follow the last string plus one space (0x00F13A70).
  const HEAVY = ["wood", "marble", "sculpture", "black_marble"];
  const VENDOR_PORTRAIT = { fleece: 75, horses: 78, armor: 74, olive_oil: 76, wine: 77 };
  const MINER = { mint: 0, foundry: 1, orichalc_refinery: 2, marble_quarry: 3 };
  function drawFigure(sel, L, T, cols, rows, cart, wt, WI) {
    const t = sel.type, F = "11CB";
    const name = s => wt(28, (Build.cat[s] || {}).zeus_id);    // 28:type of a building key
    const icons = (goods, x, y, step) => goods.forEach((k, i) => { const ic = icon(k); if (ic) uiPut(ic, x + step * i, y); });
    if (t === 19 || t === 20 || t === 21) {      // traders: no portrait, name or thought
      chain(L + 0x28, T + 0x6e, F, [wt(64, t), sel.city || ""]);
      const traded = Object.keys(sel.bought || {}).length + Object.keys(sel.sold || {}).length > 0;
      const st = t === 20 ? (sel.state === "trade" ? 7 : sel.state === "leave" ? 8 : 9)      // ship 129:6..9
        : sel.state === "trade" ? 10 : sel.state === "leave" ? (traded ? 8 : 13) : 12;     // caravan 129:8/10/12/13
      line(wt(129, st), L + 0x28, T + 0x96, F);
      // with trades this visit (ledger 0x008F9868 / 0x008F988C): "Bought" / "Sold" + count and icon per good
      // (pen + 25 after each icon); else "Buys" / "Sells" + the icons of the city's goods with quota left
      const row = (label, y, goods, counts) => {
        let p = chain(L + 0x28, y, F, [wt(129, label)]);
        const R = D.resource_ids || {};
        for (const k of [...goods].sort((a, c) => (R[a] || 99) - (R[c] || 99))) {    // goods in id order (1..22)
          if (counts) p += chain(L + 0x28 + p, y, F, [num(counts[k], "@", " ")]);
          const ic = icon(k);
          if (ic) uiPut(ic, L + 0x28 + p, y - 3);
          p += 25;
        }
      };
      if (traded) { row(4, T + 0xaa, Object.keys(sel.bought || {}), sel.bought); row(5, T + 200, Object.keys(sel.sold || {}), sel.sold); }
      else { row(2, T + 0xaa, sel.buys || []); row(3, T + 200, sel.sells || []); }
      return;
    }
    rims(L + 0x18, T + 0x66, (cols - 3) * 16, cart ? 0xa7 : 0x7a, false);
    if (t === 67 || t === 68 || t === 69) {       // god / monster / hero (cases 0x43..0x45): by its id (Figure+0x60)
      const pr = WI.portraits && WI.portraits[t] && WI.portraits[t][sel.res];
      const ps = pr && sprite(pr[0], pr[1]);
      if (ps) uiPut(ps, L + 0x1c, T + 0x70);
      uiText(wt(t === 67 ? 157 : t === 68 ? 190 : 185, sel.res), L + 0x5a, T + 0x6c, FONT("22C2"));
      const th = sel.thought ? wt(sel.thought[0], sel.thought[1]) : "";
      if (t === 67) {                             // title 158:id, 83:unfriendly, the phrase at +0xb2 in 0x15a
        line(wt(158, sel.res), L + 0x5a, T + 0x8a, F);
        line(wt(83, sel.unfriendly || 0), L + 0x5a, T + 0x9e, F);
        if (th) para(th, L + 0x5a, T + 0xb2, 0x15a, F);
        return;
      }
      if (t === 69) line(wt(64, 69), L + 0x5a, T + 0x8b, F);
      if (th) para(th, L + 0x5a, T + 0xa0, (cols - 9) * 16, F);
      if (t === 69) tellMore(sel, L, T, WI);
      return;
    }
    let pi = t;                                   // portrait exceptions (FUN_00573880)
    if (cart) pi = HEAVY.includes(sel.good) && sel.amount > 0 ? 80 : 9;
    else if (t === 37) pi = VENDOR_PORTRAIT[Object.keys(sel.load || {})[0] || ""] || 37;
    else if (t === 62) pi = sel.home === "marble_quarry" ? 72 : sel.home === "foundry" ? 73 : 62;
    if (t != null) uiPut(sprite(WI.portrait.file, WI.portrait.first + pi), L + 0x1c, T + 0x70);
    if (sel.name) uiText(wt(sel.name[0], sel.name[1]), L + 0x5a, T + 0x6c, FONT("22C2"));
    const th = sel.thought ? wt(sel.thought[0], sel.thought[1]) : "";
    if (cart) {
      chain(L + 0x5c, T + 0x8b, F, [name(sel.home), wt(64, 4)]);
      if (sel.good && sel.amount > 0) {
        const ic = icon(sel.good);
        if (ic) uiPut(ic, L + 0x5c, T + 0x9b);
        const n = Math.ceil(sel.amount / (sel.good === "sculpture" ? 400 : 100));
        const blk = sel.good === "marble" || sel.good === "black_marble";
        chain(L + 0x6e, T + 0x9d, F, [num(n, " ", ""), wt(8, (blk ? 60 : 58) + (n === 1 ? 0 : 1)), wt(23, (D.resource_ids || {})[sel.good])]);
      }
      if (sel.dest) chain(L + 0x3c, T + 0x127, "11C", sel.returning
        ? [wt(129, 16), name(sel.home), wt(129, 14), name(sel.dest)] : [wt(129, 15), name(sel.dest), wt(129, 14), name(sel.home)]);
      if (th) para(th, L + 0x28, T + 0xd2, (cols - 4) * 16, F);
      return;
    }
    if (t === 48 || t === 49 || t === 50 || t === 51) {   // animals
      line(sel.role === "deer" ? wt(129, 23) : wt(64, t), L + 0x5c, T + 0x76, F);
      return;
    }
    const tline = t === 62 && MINER[sel.home] != null ? wt(274, MINER[sel.home]) : wt(64, t);
    if (t === 26) {                               // peddler: "Sells" + the agora's goods
      const p = chain(L + 0x5c, T + 0x8b, F, [tline, wt(129, 3)]);
      icons(sel.sells || [], L + 0x5c + p, T + 0x87, 32);
    } else if (t === 37) {                        // agora vendor: Collecting / Returning with
      const p = chain(L + 0x5c, T + 0x8b, F, [tline, wt(129, sel.returning ? 18 : 17)]);
      icons(Object.keys(sel.load || {}), L + 0x5c + p, T + 0x87, 32);
    } else if (t === 47) {
      const p = chain(L + 0x5c, T + 0x8b, F, [tline, wt(129, 21)]);
      icons(sel.good ? [sel.good] : [], L + 0x5c + p, T + 0x87, 32);
    } else if (t === 53 && sel.returning) {
      const p = chain(L + 0x5c, T + 0x8b, F, [tline, wt(129, 18)]);
      icons(["meat"], L + 0x5e + p, T + 0x87, 32);
    } else if (t != null) line(tline, L + 0x5c, T + 0x8b, F);
    if (th) para(th, L + 0x5a, T + 0xa0, (cols - 9) * 16, F);
    tellMore(sel, L, T, WI);
  }
  // 'Tell me more' (table 0x005EE920 at (L+0x1A2, T+0xCC), SPR_TELL_ME_MORE_BTN): for a figure with the mood
  // flag while another mood weight is >= 2; a click (0x005ABE80) zeroes the shown one and shows the next (the
  // exe's pick compares a weight with an index: copied as is)
  function tellMore(sel, L, T, WI) {
    const W = sel.weights;
    if (W && sel.thought && W.some((v, i) => v >= 2 && i !== sel.thought[1])) {
      const bx = L + 0x1a2, by = T + 0xcc, hov = uiHover(bx, by, 16, 16);
      uiPut(sprite("Zeus_Interface", WI.tell_more + (hov ? 1 : 0)), bx, by);
      UIX.hits.push([bx, by, 16, 16, () => {
        const ph = sel.thought[1];
        if (ph === 6) return;
        if (ph < 5) W[ph] = 0;
        let best = 0;
        for (let i = 0; i < 5; i++) if (W[i] > best) best = i;
        if (W[best] > 1) { W[best] = 0; sel.thought = [sel.thought[0], best]; }
      }, "Tell me more"]);
    }
  }

  return { init: d => { D = d; }, ready, size, draw, target, panelOf, drawWalkers, rims };
})();
window.ZInfo = ZInfo;
