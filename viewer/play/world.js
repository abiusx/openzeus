// The world map screen (docs/logic/world-map.md section 3, docs/play/world.md): the map picture, cities,
// trade routes, armies, the side panel with the selected city and the diplomacy buttons and dialogs.
// Data: /data/play/world.json (tools/play_world.py: the exe's widget table, strings, layout) and the
// server's /world.json (sim/empire export). Presentation only: every action is a sim command (POST /cmd).
// Hooks (ui.js): the control panel's world map button toggles it; uiDraw draws it instead of the panel;
// uiDown/inUI route the mouse to it while it is open.
"use strict";

const WorldMap = (() => {
  // the map area's width = the side panel's x: the city panel's x, 16 px more at 800 wide or less (FUN_00597E20;
  // oracle 1L5-reqbtn wm_knossos.bmp at 800 x 600: the panel at 614 = 800 - 186; bugs.md 352)
  const mapW = () => UIX.panelX + (UIX.W > 800 ? 0 : 16);
  let D = null, loading = false;                // data/play/world.json
  let W = null, fetching = false, lastFetch = 0; // /world.json
  let quests = [];                               // open god quests (/heroes.json, sim/heroes): their city's requests list
  let open = false, sel = null, dialog = null, scroll = [0, 0];
  let colony = null;                             // the colony choice (screen 0x34): {options, pick, onPick}
  const pics = {};                              // picture number -> sprite (own sheet)
  const GOOD_IDS = { urchin: 1, fish: 2, meat: 3, cheese: 4, carrots: 5, onions: 6, wheat: 7, oranges: 8, wood: 9,
    bronze: 10, marble: 11, grapes: 12, olives: 13, fleece: 14, horses: 15, black_marble: 16, orichalc: 17, armor: 18,
    sculpture: 19, olive_oil: 20, wine: 21, chariot: 22, drachmas: 23, troops: 24, food: 25, strike: 27 };
  const F = f => "SPR_FONTS_" + f;
  const LABEL_555 = 0x7F39;                     // city label colour (world_map_draw 0x00599DA0)
  const txt = (g, i) => (D && D.texts[String(g)] && D.texts[String(g)][i]) || "";
  const itemName = it => it === "strike" ? "military strike" : txt(23, GOOD_IDS[it]) || it;
  const city = id => W && W.cities.find(c => c.id === id);
  const iface = (name, k = 0) => groupSprite("Zeus_Interface", name, k);
  // Text in a box of width w (bugs.md 124): word-wrapped as the exe's paragraph_draw (0x005090A0) when it does
  // not fit; opts.center centres each line in w; opts.lines caps the line count (fixed rows). A line still wider
  // than w (one long word, or past the cap) is recorded in `overflow` (checked by WorldMap.overflow in tests).
  let overflow = [], dlgRect = null;
  const stepOf = font => window.ZText ? ZText.draw(() => {}, font, "A", 0, 0).height : 16;
  function boxLines(str, font, w) {
    str = String(str);
    if (!window.ZText) return [str];
    const wrapTo = ww => ZText.wrap(font, str, ww).map(l => l.replace(/^ /, ""));
    let lines = ZText.measure(font, str) <= w ? [str] : wrapTo(w);
    // the exe's wrap counts glyph + 1 per letter, measure() its centring width: tighten until every line fits
    for (let ww = w - 4; ww > w / 2 && lines.some(l => ZText.measure(font, l) > w); ww -= 4) lines = wrapTo(ww);
    return lines;
  }
  function box(str, x, y, font, w, opts = {}) {
    if (str == null || str === "") return 0;
    str = String(str);
    const step = stepOf(font);
    let lines = boxLines(str, font, w);
    if (opts.lines && lines.length > opts.lines) {          // fixed rows: keep one line, report it
      overflow.push({ str, w, lines: lines.length, cap: opts.lines });
      lines = [str];
    }
    lines.forEach((l, k) => {
      if (window.ZText && ZText.measure(font, l) > w) overflow.push({ str: l, w, width: ZText.measure(font, l) });
      // a wrapped line keeps the space it was broken at in the exe's centring: oracle wm_rival3 / wm_ally2 lines 2..3
      // sit 3 px (half a space) right of a centred bare line (bugs.md 204)
      uiText(opts.center && k > 0 ? " " + l : l, x, y + k * step, font, opts.center ? { center: w } : {});
    });
    return lines.length * step;
  }

  async function load() {
    if (D || loading) return;
    loading = true;
    try { D = await getJSON("/data/play/world.json"); } catch (e) { console.warn("world.json", e); }
    loading = false;
  }
  // Every second while the city is held; ours (user 11-04, "Pause on the world map" off: the city runs under the map)
  // every 400 ms while it runs, so armies, cities, trade and requests follow the sim (docs/play/world.md "Running city")
  const running = () => typeof P !== "undefined" && P.live && P.playing;
  async function refresh(force) {
    if (fetching || (!force && performance.now() - lastFetch < (running() ? 400 : 1000))) return;
    fetching = true;
    try { W = await getJSON("/world.json"); lastFetch = performance.now(); } catch (e) { }
    try { quests = ((await getJSON("/heroes.json")).quests || []).filter(q => q.state === 0); } catch (e) { quests = []; }
    fetching = false;
  }
  // The picture: a sheet of its own (gl.js binds the sheets a draw uses, docs/play/gpu.md), its texture replaced when
  // the picture changes and shrunk to 1 px on close.
  let shown = 0, sheet = -1;
  function picture(R, n) {
    if (pics[n] === undefined) {
      pics[n] = null;
      const img = new Image();
      img.onload = () => { pics[n] = img; };
      img.src = D.pictures[Math.max(1, Math.min(10, n || 1)) - 1];
    }
    const img = pics[n];
    if (!img) return null;
    if (sheet < 0) sheet = R.addSheet(img, { what: "world map picture" });
    else if (shown !== n) R.setSheet(sheet, img);
    shown = n;
    return { sheet, x: 0, y: 0, w: img.width, h: img.height, ax: 0, ay: 0 };
  }

  function toggle() {
    if (open) { close(); return; }
    load();
    refresh(true);
    open = true; dialog = null; zf = 1; scroll = [0, 0];           // opens at fit
  }
  function close() {
    open = false; dialog = null; colony = null;
    if (sheet >= 0 && shown) {                     // free the picture's texels
      const c = document.createElement("canvas");
      c.width = c.height = 1;
      R.setSheet(sheet, c);
    }
    shown = 0;
  }
  const isOpen = () => open;
  // ours (user 11-04): while the city runs under the map, message windows and offers pop up over it (the exe paused
  // and had none); held while the map pauses, or a dialog / the colony choice / the army dialog is up
  const holdsPopups = () => open && ((typeof PAUSE !== "undefined" && PAUSE.world) || !!dialog || !!colony
    || !!(window.MilPanel && MilPanel.armyOpen()));

  // --- geometry: the map viewport (x 0..panelX, y 30..H) --------------------------------------------------
  // The exe shows its 838 x 738 picture whole beside the panel at 1024 x 768 (scroll only at 800 x 600). Ours
  // (docs/play/world.md "Zoom"; screen-size adaptation): the picture opens at "fit" (whole, centred, scaled to
  // the map area: k = min(vw / pw, vh / ph)); zoom in from there (wheel, E/Q, the bar's -/+, up to 4x the picture's
  // pixels), zoomed out stops at fit; scrolling (edge, WASD/arrows) only while it is larger than the area.
  // scroll: the scaled picture's offset in UI px. Everything on the map (picture, routes, cities, labels,
  // armies) is cut to the viewport `clip` (bugs.md 180) and placed through put() (picture px -> UI px).
  let zf = 1;                                   // zoom relative to fit (>= 1)
  const MAX_K = 4;
  function view() {
    const vw = mapW(), vh = UIX.H - 30, pw = D.picture_size[0], ph = D.picture_size[1];
    const fit = Math.min(vw / pw, vh / ph);
    zf = Math.max(1, Math.min(zf, Math.max(1, MAX_K / fit)));
    const k = fit * zf, sw = pw * k, sh = ph * k;
    scroll[0] = Math.max(0, Math.min(scroll[0], sw - vw)); scroll[1] = Math.max(0, Math.min(scroll[1], sh - vh));
    const ox = sw <= vw ? Math.round((vw - sw) / 2) : -Math.round(scroll[0]);
    const oy = 30 + (sh <= vh ? Math.round((vh - sh) / 2) : -Math.round(scroll[1]));
    // mx: where picture x 0 lands for everything drawn on it (routes, markers, names, armies, the click test). The exe
    // (world_map_draw 0x00599DA0) clamps its scroll x to picture w - view w - 1 when it reaches that, then 0 for the
    // picture only and restores the -1 for the rest: with the whole width shown (1024 x 768: picture 838 = view)
    // every marker sits 1 px right of the picture (oracle worldmap/wm0: icons, names and route dots +1 x, not y)
    const mx = ox + (sw <= vw ? k : 0);
    return { vw, vh, ox, oy, mx, pw, ph, k, fit, clip: [0, 30, vw, UIX.H] };
  }
  // a sprite at picture px (x, y) on the marker origin, drawn at its size x k, cut to the viewport
  const put = (v, sp, x, y) => sp && uiPutClip(sp, v.mx + x * v.k, v.oy + y * v.k, v.clip, sp.w * v.k, sp.h * v.k);
  // zoom by f about UI point (mx, my) (the map's centre when it is not over the map)
  function zoomBy(f, mx, my) {
    if (!D || !open) return;
    const v = view();
    if (!(mx >= 0 && mx < v.vw && my >= 30 && my < UIX.H)) { mx = v.vw / 2; my = 30 + v.vh / 2; }
    const px = (mx - v.ox) / v.k, py = (my - v.oy) / v.k;
    zf *= f;
    const w = view();                           // clamps zf
    scroll[0] = px * w.k - mx; scroll[1] = py * w.k - (my - 30);
  }
  function iconRect(c) {                        // world object: centred on (x, y), its size (+0x08/+0x0A)
    const m = c.map;
    return [m.x - Math.trunc(m.w / 2), m.y - Math.trunc(m.h / 2), m.w, m.h];
  }

  // --- drawing ---------------------------------------------------------------------------------------
  function draw(R) {
    if (!D) { load(); return; }
    overflow = [];
    refresh();
    const v0 = view();
    // edge scroll when the picture is larger than the view (the exe at 800 x 600; ours when zoomed in)
    const [mx, my] = UIX.mouse;
    if (!dialog && mx >= 0 && mx < v0.vw && my >= 30) {
      if (mx < 8) scroll[0] -= 8; else if (mx > v0.vw - 8) scroll[0] += 8;
      if (my < 38) scroll[1] -= 8; else if (my > UIX.H - 8) scroll[1] += 8;
    }
    // ours (user 10-29): the city's pan keys (WASD / arrows, play.js PAN) scroll the picture too, 8 px a frame
    if (!dialog && typeof keys !== "undefined") for (const k of keys) if (PAN[k]) { scroll[0] += PAN[k][0] * 8; scroll[1] += PAN[k][1] * 8; }
    const v = view();
    uiPut(UIX.black, 0, 30, 1, mapW(), UIX.H - 30);          // beyond the picture (bigger windows)
    const pic = W && picture(R, W.picture);
    if (pic) uiPutClip(pic, v.ox, v.oy, v.clip, pic.w * v.k, pic.h * v.k);
    if (colony) {                                  // screen 0x34: the picture, the colonies to found, the panel's texts
      drawColony(v);
      drawColonyPanel();
      return;
    }
    if (W && !W.off) {
      drawRoutes(v);
      const labels = drawCities(v);
      drawArmies(v);
      // city names over every marker and army (as before, when they were on the text layer): the mask font
      // SPR_FONTS in 0x7F39 (world_map_draw 0x00599DA0: string_draw(name, x, y, font group 0, 0x7F39); 0xFE59 in
      // 565 mode, the same colour), no shadow; gl.js draws alpha -(2 + colour) as that solid colour
      const tint = (sp, gx, gy) => sp && uiClipPush((s, px, py, w, h) => uiPut(s, px, py, -(2 + LABEL_555), w, h),
                                                     sp, v.mx + gx * v.k, v.oy + gy * v.k, v.clip, sp.w * v.k, sp.h * v.k);
      if (window.ZText) for (const [str, lx, ly] of labels) ZText.draw(tint, "SPR_FONTS", str, lx, ly);
    }
    if (W && W.off) drawOff(v);
    drawPanel();
    if (dialog) drawDialog();
  }

  // Module off (`empire off`, saves from before sim/empire; bugs.md 125): the scenario's picture, no markers (the
  // data/trade.json partners have no map position, so none is invented), a centred frame naming them instead.
  const OFF_PANEL = "World map off";
  function drawOff(v) {
    const w = 432, cols = w / 16, tw = w - 48;
    const para = "This game predates the world module (empire off): no cities on the map, no diplomacy."
      + " Its trade partners come from data/trade.json and have no place on the map:";
    const step = stepOf(F("11C"));
    const pl = boxLines(para, F("11C"), tw).length;
    const ps = W.partners || [];
    const h = 50 + pl * step + 10 + ps.length * 20 + 30, nrows = Math.ceil(h / 16);
    const vw = Math.min(mapW(), v.vw), x = Math.max(0, Math.trunc((vw - w) / 2)), y = Math.max(32, 30 + Math.trunc((UIX.H - 30 - nrows * 16) / 2));
    uiFrame("titled", x, y, cols, nrows);
    box(OFF_PANEL, x + 16, y + 12, F("22C"), w - 32, { center: true });
    let yy = y + 46 + box(para, x + 24, y + 46, F("11C"), tw) + 10;
    for (const p of ps) {
      box(`${p.name} (${p.route})${p.post ? ": post built" : ""}`, x + 24, yy, F("11C"), tw, { lines: 1 });
      yy += 20;
    }
  }

  function drawRoutes(v) {
    for (const r of W.routes) {
      const sp = iface(r.kind === "sea" ? "SPR_SEA_ROUTE" : "SPR_LAND_ROUTE");
      for (const [x, y] of r.dots) put(v, sp, x, y);
    }
  }

  function drawCities(v) {
    const t = performance.now(), labels = [];
    for (const c of W.cities) {
      if (!c.map || !c.shown) continue;
      const [x, y, w, h] = iconRect(c);         // picture px
      const mk = c.marker, base = iface(mk.base[0], mk.base[1]);
      put(v, base, x, y);
      const tw = window.ZText ? ZText.measure("SPR_FONTS", c.name) : 5 * c.name.length;   // string_width, font group 0
      const lab = c.map.label;
      const lx = lab === "left" ? x - tw : lab === "right" ? x + w : x + Math.trunc((w - tw) / 2);
      const ly = lab === "left" || lab === "right" ? y + Math.trunc(h / 2) : lab === "top" ? y - 10 : y + h + 5;
      // Drawn as sprites after the markers (scaled with the picture), so the panel and dialogs drawn later cover it.
      labels.push([c.name, lx, ly]);
      if (!c.active) continue;
      if (mk.standard) {                         // the icon's top-right; the ally banner waves (5 frames)
        const g = atlas.Zeus_Interface && atlas.Zeus_Interface.groups[mk.standard];
        const k = g && g[1] > 1 ? Math.floor(t / 120) % g[1] : 0;
        const sp = iface(mk.standard, k);
        if (sp) put(v, sp, x + w, y + h - sp.h);
      }
      if (mk.army != null) { const sp = iface("SPR_EMP_MILITARY_STRENGTH", mk.army); if (sp) put(v, sp, x + Math.trunc(w / 2) - sp.w, y - sp.h); }
      if (mk.wealth != null) { const sp = iface("SPR_EMP_ECONOMIC_STRENGTH", mk.wealth); if (sp) put(v, sp, x + Math.trunc(w / 2), y - sp.h); }
      if (mk.rebelling) {
        const g = atlas.Zeus_Interface.groups.SPR_EMP_REBELLING;
        const sp = iface("SPR_EMP_REBELLING", g ? Math.floor(t / 120) % g[1] : 0);
        if (sp) put(v, sp, x + Math.trunc(w / 2) - 6, y + Math.trunc(h / 2) - 12);
      }
    }
    return labels;
  }

  const ARMY_LAND = ["SPR_EMP_ARMY_GREEK_NP", "SPR_EMP_ARMY_TROJAN", "SPR_EMP_ARMY_PERSIAN", "SPR_EMP_ARMY_CENTAUR", "SPR_EMP_ARMY_AMAZON"];
  function drawArmies(v) {                      // 0x00599590: player / others, land / sea, size 0..2
    // world_map_draw_army 0x00599740: the army picture centred on its point (+0x77 = 0: hidden, only its heroes);
    // the heroes away on its event (war.army_heroes) at the picture's top-left + table 0x00644E68: (0,0) (10,10)
    // (-10,-10) without the picture, (10,10) (-10,-10) (10,-10) with it; SPR_EMP_HEROES + hero (6 / 7, Poseidon's,
    // from another file: not drawn)
    const OFF = [[0, 0], [10, 10], [-10, -10], [10, -10]];
    for (const a of W.armies) {
      const g = a.who === "player" ? (a.sea ? "SPR_EMP_NAVY_PLAYER" : "SPR_EMP_ARMY_GREEK_P")
                                   : (a.sea ? "SPR_EMP_NAVY_NP" : ARMY_LAND[a.nation] || ARMY_LAND[0]);
      const sp = iface(g, a.size);
      if (!sp) continue;
      const x0 = a.x - Math.trunc(sp.w / 2), y0 = a.y - Math.trunc(sp.h / 2);
      if (!a.hidden) put(v, sp, x0, y0);
      (a.heroes || []).filter(h => h < 6).forEach((h, k) => {
        const o = OFF[k + (a.hidden ? 0 : 1)], hs = iface("SPR_EMP_HEROES", h);
        if (hs) put(v, hs, x0 + o[0], y0 + o[1]);
      });
    }
  }

  // --- the side panel (FUN_005981B0) -------------------------------------------------------------------
  function drawPanel() {
    const X = mapW(), L = D.layout, side = sprite(D.side_panel.sprite.file, D.side_panel.sprite.index);
    if (side) {
      uiPut(side, X, 0);
      for (let y = side.h; y < uiCanvasWH()[1]; y += 6) uiPut(subSprite(side, 0, side.h - 6, side.w, 6), X, y);
      uiEdgeFill(X + side.w);                    // right of it, as the city panel (ui.js; bugs.md 216)
    }
    const c = sel != null ? city(sel) : null;
    const wd = Object.fromEntries(D.widgets.map(w => [w.name, w]));
    const b = (c && c.buttons) || {};
    const me = c && c.kind === "player";
    const act = {
      back: () => close(), help: () => Help.open(() => Help.rec("world_map"), 1),
      attitude: c && c.exists && !me ? () => { dialog = { kind: "advice" }; } : null,
      request: b.request ? () => { dialog = { kind: "request" }; } : null,
      requests: b.requests || (c && quests.some(q => q.city === c.id)) ? () => { dialog = { kind: "requests" }; } : null,
      gift: b.gift ? () => { dialog = { kind: "gift" }; } : null,
      raid: b.raid ? () => armyDialog("raid") : null,          // the army dialog (screen 0x21, milpanel.js)
      conquer: b.conquer ? () => armyDialog("conquer") : null,
      prev: () => cycle(-1), next: () => cycle(1),
      history: c && !me ? () => { dialog = { kind: "history" }; } : null,
      orders: b.orders ? () => orders(c) : null,
    };
    for (const w of D.widgets) {
      if (w.name === "orders" && !b.orders) continue;                 // hidden (state 2)
      if (w.name === "attitude" && c && (me || !c.exists)) continue;  // hidden (state 2, 0x00597E60; oracle wm_player, wm_distant7)
      const enabled = !!act[w.name] && (c || ["back", "help", "prev", "next"].includes(w.name));
      uiWidget(w, X, 0, { disabled: !enabled, onClick: enabled ? act[w.name] : null,
                          name: (w.tooltip && w.tooltip.text) || "" });
      // balloons (FUN_004F6110 screen 0x14, group 44; hover ids 13..24 = table 0x005EF488): an enabled widget's
      // text; back, help and orders have none (oracle balloons-wm: b_back / b_help / b_orders no box)
      // request: 309 "demand" when city_request_threshold(city, 0x19) == 1 (ours: a rival, the demand class of
      // world-map.md; not seen in the oracle), else 308
      const tip = { attitude: 333, request: c && c.relation === "rival" ? 309 : 308, requests: 310, gift: 311, raid: 312, conquer: c && c.rebellion ? 314 : 313,
                    prev: 331, next: 332, history: 335 }[w.name];
      if (tip && enabled && window.Balloon && !dialog && !armyUp()) Balloon.add(X + w.rect[0], w.rect[1], w.rect[2], w.rect[3], tip, false, 44);
    }
    // a city on the map under the mouse: 44:334 "Click for information" (hover id 0x9C4)
    const [mx, my] = UIX.mouse;
    if (W && window.Balloon && !dialog && !armyUp() && mx >= 0 && mx < mapW() && my >= 30 && cityAt(mx, my) != null) Balloon.add(mx, my, 1, 1, 334, false, 44);
    box(txt(47, 8), X + wd.back.rect[0], wd.back.rect[1] + 8, F("11C"), wd.back.rect[2], { center: true, lines: 1 });
    if (!c) {
      if (W && W.off) { box(OFF_PANEL, X + 21, L.click_info_y, F("11C"), 146, { center: true }); return; }
      box(txt(47, 5), X + 21, L.click_info_y, F("11C"), 146, { center: true });   // FUN_00509060(0x2F, 5, x+0x15, y+0xCA, 0x92): wrapped, centred
      return;
    }
    const bx = X + L.box_x;
    if (me) {
      box(txt(47, 0), bx, L.our_city_y, F("11C"), L.box_w, { center: true, lines: 1 });
      box(c.name, bx, L.our_name_y, F("11C"), L.box_w, { center: true, lines: 1 });
      return;
    }
    if (c.exists || c.kind === "parent") {
      const kind = c.kind === "parent" ? txt(39, 3) : txt(253, { ally: 0, rival: 1, vassal: 2, colony: 3 }[c.relation]);
      box(kind, bx, L.kind_y, F("11C"), L.box_w, { center: true, lines: 1 });
    }
    box(c.name, bx, L.name_y, F("11C"), L.box_w, { center: true, lines: 1 });
    if (c.exists && c.kind !== "parent") box(`${txt(44, 328)} ${c.leader || ""}`, bx, L.leader_y, F("9LTBK"), L.box_w, { center: true, lines: 1 });
    const aw = wd.attitude.rect;
    if (c.exists) box(c.rebellion ? txt(44, 329) : txt(65, c.word), X + aw[0], aw[1] + 8, F("11C"), aw[2], { center: true, lines: 1 });
    if (!c.exists && !c.trading) return;
    box(txt(47, 6), X + L.goods_x, L.goods_y, F("11C"), L.box_w, { center: true, lines: 1 });
    if (b.orders) { const o = wd.orders.rect; box(txt(47, 7), X + o[0], o[1] + 8, F("11C"), o[2], { center: true, lines: 1 }); }
    // Buys / Sells lists in the goods frame (inner y 172..396, read back from SPR_WORLD_SIDE_INT). The exe's
    // layout (FUN_005981B0): title at 247, its SPR_COMMOD_BOXES bar (148 x 24 per row, one picture of 1..4 rows)
    // 16 below, rows every 20 px from title + 24: the good's icon at x 29 (row - 6), the name at 54 and
    // "used/quota" centred in 129..166 (font 9DKBU); the next title 16 under the last row. The exe has 4 slots
    // per list and Zeus's cities have at most 5 goods; world files may have up to 10 (e.g. partners' Susa 4 + 4),
    // which the exe's pitch would push into the tribute box. Those (ours, bugs.md 204, was text-only 127) keep
    // the same pieces, one bar per list stretched from the 1-row picture, icons and names, at the pitch that fits.
    const lists = [[c.buys, 1, 3], [c.sells, 2, 4]].filter(l => l[0].length);
    const bottom = (L.list_bottom || 394) + 2, nRows = lists.reduce((a, l) => a + l[0].length, 0);
    const exe = lists.every(l => l[0].length <= 4) && nRows <= 5;
    const pitch = exe ? L.row_dy : Math.min(L.row_dy, Math.floor((bottom - L.list_title_y - lists.length * 20 - 2) / Math.max(1, nRows)));
    const bar1 = iface("SPR_COMMOD_BOXES", 0);
    const iconW = ic => ic ? Math.round(ic.w * Math.min(ic.h, pitch - 1) / ic.h) : 0;   // a scaled icon's width (compact)
    const nameX = exe ? L.name_dx : Math.min(L.name_dx, L.icon_dx + 3 +
      Math.max(0, ...lists.flatMap(l => l[0].map(([g]) => iconW(goodIcon(g))))));      // one column, after the widest icon
    let ty = L.list_title_y;
    for (const [list, tP, tN] of lists) {
      box(txt(47, c.trading ? tP : tN), X + L.goods_x, ty, F("11C"), L.box_w, { center: true, lines: 1 });
      const by = ty + 16;
      let ry;                                       // the rows' top (the exe's icon y = text y - 6)
      if (exe) {
        const frame = iface("SPR_COMMOD_BOXES", list.length - 1);
        if (frame) uiPut(frame, X + L.box_dx, by);
        ry = by + 2;
      } else if (bar1) {                            // 2 px top edge, the middle stretched, 2 px bottom edge
        const h = 4 + pitch * list.length;
        uiPut(subSprite(bar1, 0, 0, bar1.w, 2), X + L.box_dx, by);
        uiPut(subSprite(bar1, 0, 2, bar1.w, bar1.h - 4), X + L.box_dx, by + 2, 1, bar1.w, h - 4);
        uiPut(subSprite(bar1, 0, bar1.h - 2, bar1.w, 2), X + L.box_dx, by + h - 2);
        ry = by + 2;
      }
      for (const [good, used, quota] of list) {
        const q = `${used}/${Math.max(used, quota)}`;                  // exe: "%d/%d", the quota raised to used
        const ty2 = ry + Math.floor((pitch - 8) / 2);                   // text y (exe: row + 6)
        const ic = goodIcon(good);
        const nx = nameX;
        if (ic && exe) uiPut(ic, X + L.icon_dx, ry);
        else if (ic) {                              // smaller icon, the names moved up to them (room for "Black Marble")
          const ih = Math.min(ic.h, pitch - 1), iw = iconW(ic);
          uiPut(ic, X + L.icon_dx, ry + Math.floor((pitch - ih) / 2), 1, iw, ih);
        }
        // the name may run up to the (centred) quota text
        const qx = c.trading && window.ZText ? L.quota_x + Math.trunc((L.quota_w - ZText.measure(F("9DKBU"), q)) / 2) - 3 : L.box_x + L.box_w;
        box(itemName(good), X + nx, ty2, F("9DKBU"), qx - nx, { lines: 1 });
        if (c.trading) box(q, X + L.quota_x, ty2, F("9DKBU"), L.quota_w, { center: true, lines: 1 });
        ry += pitch;
      }
      ty = exe ? ty + 16 + L.row_dy * list.length + 16 : by + 4 + pitch * list.length + 2;
    }
    drawTribute(c, X, L);
  }

  function drawTribute(c, X, L) {
    const t = c.tribute, x = X + L.tribute_x, y = L.tribute_y, w = L.tribute_w;
    let head = null;
    if (c.kind === "distant") head = txt(44, 325);
    else if (c.cls === "ally") head = txt(44, 323);
    else if (c.cls === "rival") head = t.mode === 2 ? txt(44, 321) : txt(44, 324);
    else if (c.cls === "vassal" || c.cls === "colony") head = txt(44, 320);
    if (!head) return;
    box(head, x, y, F(D.fonts.tribute), w, { center: true });   // wrapped as the exe (oracle wm_ally2, wm_rival3)
    const paying = (c.cls === "vassal" || c.cls === "colony") && t.good;
    const claiming = c.cls === "rival" && t.mode === 2;
    if (paying || claiming) {
      const good = claiming ? "drachmas" : t.good, amount = claiming ? t.claim_now : t.amount;
      const ic = goodIcon(good);
      if (ic) uiPut(ic, X + L.tribute_icon[0] + 0, L.tribute_icon[1]);
      box(`${amount} ${itemName(good)} ${txt(44, 322)}`, X + L.tribute_amount[0], L.tribute_amount[1], F(D.fonts.tribute),
          x + w - X - L.tribute_amount[0], { lines: 1 });
      if (paying && t.mode === 0)
        box(c.rebellion ? txt(44, 327) : txt(44, 326), x, L.suspended_y, F("9DKYEL"), w, { center: true });
    }
  }

  function goodIcon(good) {
    if (good === "drachmas" || good === "troops" || good === "strike") { const r = D.icons[good]; return r && sprite(r.file, r.index); }
    const r = MAP.info_panels && MAP.info_panels.goods_icons[good];
    return r ? sprite(r.file, r.index) : null;
  }

  function cycle(d) {                            // 0x00406B30 / 0x00406BB0: active, visible cities by index
    if (!W) return;
    const ids = W.cities.filter(c => c.active && c.shown).map(c => c.id).sort((a, b) => a - b);
    if (!ids.length) return;
    const i = sel == null ? (d > 0 ? -1 : 0) : ids.indexOf(sel);
    sel = ids[(i + d + ids.length) % ids.length];
    dialog = null;
  }

  function orders(c) {                           // 0x00406940: the bound post's info window
    if (!c.post) return;
    const b = (typeof S !== "undefined" && S.buildings || []).find(x => x.id === c.post.id);
    close();
    cam.x = tileX(c.post.x, c.post.y) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
    cam.y = tileY(c.post.x, c.post.y) - innerHeight / 2 / cam.zoom;
    if (b) openInfo(b, innerWidth / 2, innerHeight / 2);
  }

  // --- dialogs (screen 0x1A): advice, request, gift, gift size, requests, history; raid / conquer: milpanel.js --
  function armyDialog(kind) {
    const c = city(sel);
    if (!window.MilPanel) return;                 // the army dialog (screen 0x21) is milpanel.js's
    if (window.Military) Military.refresh();
    const allies = W.cities.filter(o => o.id !== c.id && (o.asks || []).some(q => q.item === "strike" && q.ok)).map(o => o.name);
    MilPanel.openArmy(c.name, kind, c.route, (c.sells || []).map(s => Array.isArray(s) ? s[0] : s), allies);
  }

  async function cmd(line) {
    const seq = await sendCommands([line], { sound: false });
    dialog = null;
    refresh(true);
    return seq;
  }

  // The dialogs of screen 0x1A, drawn by FUN_00464C00 by the mode at 0x00903440 (docs/play/world.md "Dialogs";
  // checked against oracle 1F-wmdlg1/2): 0 favour advice, 1 request, 2 gift, 3 gift size, 5 the city's requests,
  // 6 history. Every geometry is the exe's: the dialog centred on the map area (FUN_00597E20: panel x + 16, - 16
  // above 800 wide) and the screen height; rows are the builders' rects relative to the dialog. A right click goes
  // back one level (gift size -> gift list) or to the map.
  const fill = (s, t) => String(s).replace("[city_name]", t.city ?? "").replace("[item]", t.item ?? "").replace("[amount]", t.amount ?? "");
  const plural = it => txt(98, GOOD_IDS[it]) || itemName(it);          // [item]: group 98 ("skeins of fleece")
  const byId = (a, b) => (GOOD_IDS[a] ?? 99) - (GOOD_IDS[b] ?? 99);
  // the row icon by item (FUN_00464C00's switch): drachmas / troops / strike the request icons, food goods icon 0x13
  const rowIcon = it => it === "food" ? sprite(D.dialog_icons.food.file, D.dialog_icons.food.index) : goodIcon(it);
  const dsprite = k => sprite(D.dialog_icons[k].file, D.dialog_icons[k].index);
  const rims = (x, y, w, h, hov) => window.Options && Options.rims(x, y, w, h, hov);
  const line = (s, x, y, font, w = 600) => box(s, x, y, F(font), w, { lines: 1 });
  const sbar = (x, y, h, n, vis, st) => {          // scrollbar 0x005A0A70 (help.js): only with more rows than fit
    st.range = Math.max(0, n - vis); st.scroll = Math.max(0, Math.min(st.scroll || 0, st.range));
    if (n > vis && window.Help) Help.scrollbar(x, y, h, st);
  };
  function frameAt(x, y, w, h, cols, rows) {
    uiFrame("titled", x, y, cols, rows);
    dlgRect = [x, y, cols * 16, rows * 16];
    UIX.hits.push([x, y, cols * 16, rows * 16, null, "dialog"]);    // swallow clicks inside
  }

  // request text by city_can_request's code and city_request_threshold (0x004636B0 / FUN_00464C00 mode 1)
  function askText(a) {
    const troops = a.item === "troops", strike = a.item === "strike", food = a.item === "food";
    let k;
    if (a.code === 3 && a.thr >= 0 && a.thr <= 3) k = troops ? 7 : strike ? 8 : 3 + a.thr;
    else if (a.code === 0) k = troops ? 13 : strike ? 14 : food ? 16 : 15;
    else if (a.code === 1) k = troops ? 17 : 18;
    else if (a.code === 2) k = troops ? 9 : strike ? 10 : food ? 12 : 11;
    else k = 12;
    return { text: txt(41, k), on: a.code === 3 && a.thr >= 0 && a.thr <= 3 };
  }

  function drawDialog() {
    const c = city(sel), d = dialog;
    if (!c) { dialog = null; return; }
    drawDialog1(d, c);
  }
  function drawDialog1(d, c) {
    const MW = mapW(), H = UIX.H, tok = { city: c.name };
    if (d.kind === "advice") {                     // mode 0, FUN_00465330 + FUN_004652C0
      const x = Math.trunc((MW - 480) / 2), y = Math.trunc((H - 368) / 2), ix = x + 16, iy = y + 64, iw = 448;
      frameAt(x, y, 480, 368, 30, 23);
      uiFrame("plain", ix, iy, 28, 18);
      dialogTitle(txt(44, 290), ix, y + 16, iw, "22C");
      const k = adviceIndex(c);
      // text_ref_paragraph_draw: paragraph_draw 0x005090A0 (a wrapped line keeps the space it broke at)
      if (k != null) uiText(txt(92, k), ix + 8, iy + 8, F("11C2"), { width: iw - 16 });
      return;
    }
    if (d.kind === "request") {                    // mode 1, builder 0x00465070
      const asks = (c.asks || []).slice().sort((a, b) => byId(a.item, b.item));
      const n = asks.length, w = 520, h = Math.max(1, n) * 28 + 60, x = Math.trunc((MW - w) / 2), y = Math.trunc((H - h) / 2);
      frameAt(x, y, w, h, (w + 15) >> 4, (h + 15) >> 4);
      dialogTitle(fill(txt(41, 1), tok), x, y + 16, w, "9LTBK");
      asks.forEach((a, i) => {
        const ry = y + 40 + 28 * i, { text, on } = askText(a);
        const s = fill(text, { item: plural(a.item === "food" ? "food" : a.item) });
        if (on) {
          const hov = d.frozen != null ? d.frozen === i + 1 : uiHover(x + 20, ry, 480, 27);   // frozen: under a popup
          rims(x + 20, ry, 480, 27, hov);
          const ic = rowIcon(a.item);
          if (ic) uiPut(ic, x + 25, ry + 3);
          line(s, x + 50, ry + 10, "9LTBK", 460);
          UIX.hits.push([x + 20, ry, 480, 27, a.item === "strike" ? () => strikeOpen(c, i + 1)
                                                                   : () => cmd(`request ${c.id} ${a.item}`), s]);
        } else line(s, x + 20, ry + 10, "9LTBK", 480);
      });
      if (!n) line(txt(41, 19), x + 20, y + 50, "9LTBK", 480);
      return;
    }
    if (d.kind === "gift") {                       // mode 2, builder FUN_00464EE0
      const items = Object.keys(c.gifts || {}).filter(it => (c.gifts[it] || []).length).sort(byId);
      const n = items.length, w = 200, h = Math.max(1, n) * 28 + 60, x = Math.trunc((MW - w) / 2), y = Math.trunc((H - h) / 2);
      frameAt(x, y, w, h, (w + 15) >> 4, (h + 15) >> 4);
      dialogTitle(fill(txt(41, 0), tok), x, y + 16, w, "9LTBK");
      items.forEach((it, i) => {
        const ry = y + 40 + 28 * i;
        rims(x + 20, ry, 160, 27, uiHover(x + 20, ry, 160, 27));
        const ic = rowIcon(it);
        if (ic) uiPut(ic, x + 25, ry + 3);
        line(txt(23, GOOD_IDS[it]), x + 50, ry + 10, "9LTBK", 130);
        UIX.hits.push([x + 20, ry, 160, 27, () => { dialog = { kind: "giftsize", item: it }; }, itemName(it)]);
      });
      if (!n) line(txt(41, 20), x + 20, y + 50, "9LTBK", 180);
      return;
    }
    if (d.kind === "giftsize") {                   // mode 3, gift_size_dialog 0x00463E40; rows table 0x005FB900
      const sizes = (c.gifts || {})[d.item] || [], w = 300, h = 144, x = Math.trunc((MW - w) / 2), y = Math.trunc((H - h) / 2);
      frameAt(x, y, w, h, (w + 0x41) >> 4, (h + 15) >> 4);            // 22 columns: the exe's + 0x41
      dialogTitle(fill(txt(41, 0), tok), x, y + 16, w, "9LTBK");
      const units = { small: 400, medium: 800, large: 1600 }, money = { small: 500, medium: 1000, large: 2500 };
      ["small", "medium", "large"].slice(0, sizes.length).forEach((s, k) => {
        const ry = y + 40 + 28 * k;
        const n = d.item === "drachmas" ? money[s] : units[s] / (d.item === "sculpture" ? 400 : 100);
        rims(x + 20, ry, 310, 24, uiHover(x + 20, ry, 310, 24));
        const ic = rowIcon(d.item);
        if (ic) uiPut(ic, x + 25, ry + 3);
        const str = fill(txt(41, 22 + k), { amount: n, item: plural(d.item) });
        line(str, x + 20 + 0x2C, ry + 10, "9LTBK", 266);
        UIX.hits.push([x + 20, ry, 310, 24, () => cmd(`gift ${c.id} ${d.item} ${sizes[k]}`), str]);
      });
      return;
    }
    if (d.kind === "requests") {                   // mode 5, builder world_map_btn4 0x00406B00; rows 0x005FB958
      const w = 496, h = 416, x = Math.trunc((MW - w) / 2), y = Math.trunc((H - h) / 2);
      frameAt(x, y, w, h, (w + 15) >> 4, (h + 15) >> 4);
      uiFrame("plain", x + 32, y + 90, 26, 19);
      dialogTitle(fill(txt(41, 2), tok), x, y + 16, w, "11C");
      const reqs = c.requests || [], qs = quests.filter(q => q.city === c.id), n = reqs.length + qs.length;
      d.sb = d.sb || { scroll: 0 };
      sbar(x + 0x1C6, y + 0x60, 0x126, n, 7, d.sb);
      const first = n > 7 ? d.sb.scroll : 0;
      for (let k = 0; k < 7 && first + k < n; k++) {
        const i = first + k, ry = y + 0x66 + 42 * k, x0 = x + 0x2E, bx = x + 38, by = y + 96 + 42 * k;
        if (i >= reqs.length) {                    // ours: a god's quest (event type 4) with its city's requests
          const q = qs[i - reqs.length];
          line(`${txt(23, 26) || "Hero"}: ${q.god_name || q.god}`, x0 + 40, ry, "11CB", 360);
          rims(bx, by, 400, 40, uiHover(bx, by, 400, 40));
          UIX.hits.push([bx, by, 400, 40, () => { dialog = null; if (window.MilPanel) MilPanel.openArmy(c.name, "quest", c.route, [], [], q); }, "quest"]);
          continue;
        }
        const r = reqs[i];
        const st = dsprite(r.can ? "can" : "cannot");
        if (st) uiPut(st, x0, ry);
        const ic = rowIcon(r.item);
        if (ic) uiPut(ic, x0 + 20, ry);
        const font = r.can ? "11C2" : c.relation === "rival" ? "11C3" : "11CB";   // city +0xD4 == 1: rival
        let pen = 10;
        if (r.item !== "troops") {
          const num = ZText.numberText(r.amount, "@", " ");      // number_text_draw(n, '@', " " 0x005E8FD0)
          line(num, x0 + 40, ry, font, 60);
          pen = ZText.advance(F(font), num) + 6;
        }
        const name = r.amount > 1 || r.item === "marble" || r.item === "black_marble" ? plural(r.item) : txt(23, GOOD_IDS[r.item]);
        line(name, x0 + 40 + pen, ry, font, 230 - pen);
        if (r.item !== "troops") line(ZText.numberText(r.have || 0, "@", ""), x0 + 40, ry + 18, font, 60);
        if (r.overdue) line(txt(61, 205), x0 + 0x11C, ry, font, 110);
        else {
          line(ZText.numberText(r.months, "@", ""), x0 + 0x11C, ry + 4, font, 30);
          const mo = dsprite("months");
          if (mo) uiPut(mo, x0 + 0x13C, ry);
        }
        rims(bx, by, 400, 40, d.pop ? d.pop.row === i : uiHover(bx, by, 400, 40));   // under the popup: as at the click
        if (!d.pop) UIX.hits.push([bx, by, 400, 40, () => rowClick(c, d, r, i), name]);
      }
      if (!n) dialogTitle(txt(41, 21), x, y + Math.trunc(h / 2), w, "11CB");
      if (d.pop && window.MilPanel) { uiFlushText(); MilPanel.popup3F(d.pop.id, d.pop.ok, d.pop.cancel); }
      return;
    }
    if (d.kind === "history") {                    // mode 6, builder wm_sub_4651D0, inner rect FUN_00463270
      const w = 592, h = 368, x = Math.trunc((MW - w) / 2), y = Math.trunc((H - h) / 2);
      const hist = (c.history || []).slice().reverse(), n = hist.length, vis = Math.trunc((h - 80 - 8) / 16);
      const ix = x + 16, iy = y + 64, iw = w - 80 + (n < vis ? 0x30 : 0), ih = h - 80;
      frameAt(x, y, w, h, (w + 15) >> 4, (h + 15) >> 4);
      uiFrame("plain", ix, iy, iw >> 4, ih >> 4);
      dialogTitle(fill(txt(44, 284), tok), ix, y + 16, iw, "22C");
      d.sb = d.sb || { scroll: 0 };
      if (n >= vis) sbar(ix + 10 + iw, iy, ih, n + 1, vis + 1, d.sb);   // drawn from vis rows on (0x005A0A70)
      const first = n > vis ? d.sb.scroll : 0;
      for (let k = 0; k < vis && first + k < n; k++) {
        const e = hist[first + k], ry = iy + 8 + 16 * k, dl = e.delta || 0;
        if (dl) {                                  // SPR_THUMBS by the entry's change (+6)
          const m = dl < -65 ? 5 : dl < -33 ? 4 : dl < 0 ? 3 : dl > 32 ? (dl < 66 ? 1 : 2) : 0;
          const t = D.dialog_icons.thumbs, sp = sprite(t.file, t.index + m);
          if (sp) uiPut(sp, ix + 5, ry - 4);
        }
        const [mo, yr] = monthYear(e.month);
        line(mo, ix + 0x19, ry, "9DKBU", 40);
        yearText(yr, ix + 0x28, ry, "9DKBU");
        line(e.text, ix + 0x7D, ry, "9DKBU", iw - 0x7D - 4);
      }
      if (!n) dialogTitle(txt(44, 83), ix, iy + Math.trunc(ih / 2), iw, "9DKBU");
      return;
    }
    if (d.kind === "strike") {                     // the popups draw over the screen as it was (the exe does not redraw
      drawDialog1({ kind: "request", frozen: d.row }, c);   // what is under them): the request dialog with the clicked
      uiFlushText();                               // row hovered, the list as at the click
      if (d.list) strikeList(c, d);
      if (d.confirm) { uiFlushText(); strikeConfirm(c, d); }
      return;
    }
    dialog = null;
  }

  // The strike row (wm_sub_4066F0, item 0x1B) -> wm_sub_464D50: the cities this one would strike (FUN_0042DB70 with a
  // target: an existing rival; g_cities order) in screen 0x0F's list (FUN_005BEFE0, flags 10: city names, group 21);
  // none: the one-button popup 0x48 "Nobody to strike!" (FUN_00432380). A pick (wm_sub_4067B0) asks 0x4A "Military
  // Strike" / 0x4B "Ask [city_nameA] to attack [city_nameB] ?" with two buttons; yes (wm_sub_406740) makes the request
  // (city_player_request_create item 0x1B with the target) and the request dialog comes back (the saved screen 0x1A).
  function strikeOpen(c, row) {
    const list = W.cities.filter(o => o.id !== c.id && o.cls === "rival" && o.exists).sort((a, b) => a.id - b.id);
    dialog = list.length ? { kind: "strike", row, list } : { kind: "strike", row, confirm: 0x48 };
  }
  // FUN_005BF1E0 for one column (n <= 30): titled frame at the absolute screen point (150, 50) (wm_sub_464D50:
  // 0x0160A814 / 0x0160A818), (200 + 15) >> 4 = 13 cells wide, (n * 21 + 24) >> 4 high; item k: rect (5, 14 + 20k) ..
  // (201, 32 + 20k), its name (21:name id) centred in 196, font 11C, hovered 11LTBLUE (0x00781844 = k + 1; oracle
  // 1F-strike strike_hover / strike_hover2: lit over the item only); under the confirm it stays as at the click, the
  // picked city lit (strike_confirm).
  function strikeList(c, d) {
    const n = d.list.length, px = 150, py = 50, rows = (n * 21 + 24) >> 4;
    if (!d.confirm) UIX.hits.push([0, 0, UIX.W, UIX.H, () => { dialog = { kind: "request" }; }, ""]);   // elsewhere: back
    uiFrame("titled", px, py, 13, rows);
    if (!d.confirm) UIX.hits.push([px, py, 13 * 16, rows * 16, null, ""]);
    d.list.forEach((t, k) => {
      const rx = px + 5, ry = py + 14 + 20 * k;
      const hov = d.confirm ? d.target === t : uiHover(rx, ry, 196, 18);
      uiText(t.name, rx, ry, hov ? "SPR_FONTS_11LTBLUE" : "SPR_FONTS_11C", { center: 196 });
      if (!d.confirm) UIX.hits.push([rx, ry, 196, 18, () => { d.target = t; d.confirm = 0x4A; }, t.name]);
    });
  }
  // screen 0x3F (FUN_00432380 at the 640 x 480 origin + (0x50, 0x50); drawn by FUN_00431370): titled frame 30 x 10;
  // title 5:id 22C centred in 480 at y + 0x14; text 5:id+1 11C centred in 480 at y + 0x3C (wider than 0x1A3: a
  // paragraph 0x1A4 wide at x + 0x1E); buttons (FUN_004314C0, table 0x005EF938, the first `buttons` of them):
  // OK SPR_BUTTONS6 324 at (256, 100), cancel 328 at (192, 100), 34 x 34, + 1 hovered
  function strikeConfirm(c, d) {
    const cx = Math.trunc((UIX.W - 640) / 2) + 0x50, cy = Math.trunc((UIX.H - 480) / 2) + 0x50, two = d.confirm === 0x4A;
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiFrame("titled", cx, cy, 30, 10);
    const body = txt(5, d.confirm + 1).replace("[city_nameA]", c.name).replace("[city_nameB]", d.target ? d.target.name : "");
    uiText(txt(5, d.confirm), cx, cy + 0x14, "SPR_FONTS_22C", { center: 480 });
    if (window.ZText && ZText.advance("SPR_FONTS_11C", body) > 0x1A3) uiText(body, cx + 0x1E, cy + 0x3C, "SPR_FONTS_11C", { width: 0x1A4 });
    else uiText(body, cx, cy + 0x3C, "SPR_FONTS_11C", { center: 480 });
    const back = () => { dialog = { kind: "request" }; };      // the saved screen 0x1A, redrawn
    const ok = two ? () => { const t = d.target; back(); cmd(`request ${c.id} strike ${t.id}`); } : back;
    [[256, 324, ok, "OK"], [192, 328, back, "Cancel"]].slice(0, two ? 2 : 1).forEach(([bx, img, fn, nm]) => {
      const hov = uiHover(cx + bx, cy + 100, 34, 34);
      uiPut(sprite("Zeus_Interface", img + (hov ? 1 : 0)), cx + bx, cy + 100);
      UIX.hits.push([cx + bx, cy + 100, 34, 34, fn, nm]);
    });
  }
  // A 'requests by' row (wm_sub_4642D0): troops -> the army dialog for the record (army_dialog_open; ours: the
  // empire's own troop requests, which have no record there, are fulfilled with every company at home as before);
  // else FUN_00471D50 -> FUN_00408F50: enough (or Hermes pays) -> screen 0x3F 5:6 "Request" / 5:7 "Dispatch goods?"
  // with OK / cancel, OK = event_pay_tribute_or_gift (LAB_004010D0 -> FUN_0046DA30) and the list rebuilt; not
  // enough -> 5:8 / 5:9 "You do not have enough to fulfill the request" with OK only
  function rowClick(c, d, r, i) {
    // OK: paid, the list rebuilt and the dialog drawn again without the row (oracle 1L5-reqbtn wm_after)
    const pay = () => cmd(r.event != null ? `answer ${r.event} dispatch` : `fulfill ${c.id} ${i}`).then(() => { dialog = { kind: "requests" }; });
    if (r.item === "troops") {
      const e = r.event != null && ((typeof S !== "undefined" && S && S.events) || []).find(q => q.id === r.event);
      if (e && window.MilPanel) { dialog = null; if (window.Military) Military.refresh(); MilPanel.openArmy(c.name, "request", c.route, [], [], null, e); }
      else pay();
      return;
    }
    const back = () => { d.pop = null; };
    // 5:8 (not enough): FUN_00408f50 case -1, FUN_00432380(8, empty_function, 0): no button, right click closes (bugs.md 365)
    d.pop = r.can ? { id: 6, ok: () => { d.pop = null; pay(); }, cancel: back, row: i } : { id: 8, ok: null, cancel: null, row: i };
  }

  // string_draw_centered: one line centred in w from x (the exe does not wrap these)
  function dialogTitle(s, x, y, w, font) { box(s, x, y, F(font), w, { center: true, lines: 1 }); }

  // favour advice text (FUN_00465330): group 92, base by city_class (ally 0, rival 9, vassal 18, colony 27, parent 36);
  // + 5 when pleased (+0x168) is 50, + 6 when it is over 20, + 8 when displeased (+0x16C) is 50, + 7 over 20, else by
  // attitude (+0x164): > 80 + 0, > 60 + 1, >= 40 + 2, >= 20 + 3, else + 4
  function adviceIndex(c) {
    const base = { ally: 0, vassal: 18, rival: 9, parent: 36, colony: 27 }[c.cls];
    if (base == null) return null;
    const p = c.pleased || 0, q = c.displeased || 0, a = c.attitude;
    if (p === 50) return base + 5;
    if (p >= 21) return base + 6;
    if (q === 50) return base + 8;
    if (q >= 21) return base + 7;
    return base + (a > 80 ? 0 : a > 60 ? 1 : a >= 40 ? 2 : a >= 20 ? 3 : 4);
  }

  // a history month (months since the start) -> [25:month, year]
  function monthYear(m) {
    const y = (W && W.start_year != null ? W.start_year : -1000) + Math.floor(m / 12);
    return [txt(25, ((m % 12) + 12) % 12), y];
  }
  // year_text_draw 0x00508E50 (as lists.js): BC = number_text_draw(n, ' ', ' ') then 20:0 at the pen + one space
  function yearText(y, x, yy, font) {
    const num = ZText.numberText(Math.abs(y), " ", " ");
    if (y < 0) { line(num, x, yy, font, 80); line(txt(20, 0), x + ZText.advance(F(font), num) + 6, yy, font, 40); }
    else { line(txt(20, 1), x, yy, font, 40); line(num, x + ZText.advance(F(font), txt(20, 1)) + 6, yy, font, 80); }
  }

  // --- input (after ui.js's hit rects) ------------------------------------------------------------------
  function down(e, x, y) {
    if (colony) {                                  // colony_choice_click 0x00421AF0: a click on a colony marker picks it
      if (e.button !== 0 || x >= mapW() || y < 30) return true;
      const o = colonyAt(x, y);
      if (o) colony.pick = o;
      return true;
    }
    if (e.button === 2) {                          // back one level (gift size -> gift list), else to the map
      if (dialog && dialog.pop) dialog.pop = null;
      else if (dialog) dialog = dialog.kind === "giftsize" ? { kind: "gift" } : dialog.kind === "strike" ? { kind: "request" } : null;
      else sel = null;
      return true;
    }
    if (dialog) return true;
    if (!W || !D || x >= mapW() || y < 30) return true;
    const best = cityAt(x, y);
    if (best != null) sel = best;
    return true;
  }
  // --- the colony choice (screen 0x34, FUN_00421C70; oracle 1L4-colony c134 / c138 / c139) -------------------------
  // Each colony that can be founded (colony_index_nth(n) not active): SPR_EMP_INACTIVE_COLONY (the picked one
  // SPR_EMP_ACTIVE_COLONY) at its map spot and its name in red (0xF800, font group 0) placed by the object's label
  // side (+0x13) on that sprite's size; the side panel SPR_WORLD_SIDE_INT with the world map's widgets (table
  // 0x005EF488, no city: prev / next / help lit, the rest dim); 62:37 "Select a colony location" (a paragraph 0xDC
  // wide at (panel + 0x12, 0x17A)); after a pick: the name centred in 0x97 at (panel + 0x10, 0x41) (11C), 62:38
  // "Choose this location?" at the same place as 62:37, the colony's text (FUN_0042B890: its intro record's subtitle)
  // at (panel + 0x14, 0xB9) width 0xA0, and the proceed button (widget 0x005E9EC0 at (screen width - 0x23, 0x172):
  // ours panel + 186 - 0x23, the same place when the panel is at the right edge),
  // which founds it (POST /campaign proceed {colony: n}).
  const RED_555 = 0x7C00;
  function colonyMarks(v) {
    const out = [];
    for (const o of colony.options) {
      const c = city(o.id);
      if (!c || !c.map) continue;
      const sp = iface(colony.pick === o ? "SPR_EMP_ACTIVE_COLONY" : "SPR_EMP_INACTIVE_COLONY");
      const x = c.map.x, y = c.map.y;            // the object's position itself (not centred: FUN_00421C70)
      out.push({ o, c, sp, x, y, w: sp ? sp.w : 16, h: sp ? sp.h : 16 });
    }
    return out;
  }
  function drawColony(v) {
    const tint = (sp, gx, gy) => sp && uiClipPush((s2, px, py, w, h) => uiPut(s2, px, py, -(2 + RED_555), w, h),
                                                  sp, v.mx + gx * v.k, v.oy + gy * v.k, v.clip, sp.w * v.k, sp.h * v.k);
    for (const m of colonyMarks(v)) {
      put(v, m.sp, m.x, m.y);
      const tw = window.ZText ? ZText.measure("SPR_FONTS", m.o.name) : 5 * m.o.name.length, lab = m.c.map.label;
      const lx = lab === "left" ? m.x - tw : lab === "right" ? m.x + m.w : m.x + Math.trunc((m.w - tw) / 2);
      const ly = lab === "left" || lab === "right" ? m.y + Math.trunc(m.h / 2) : lab === "top" ? m.y - 10 : m.y + m.h + 5;
      if (window.ZText) ZText.draw(tint, "SPR_FONTS", m.o.name, lx, ly);
    }
  }
  function colonyAt(x, y) {
    const v = view(), px = (x - v.mx) / v.k, py = (y - v.oy) / v.k;      // FUN_0050B770: inside the marker
    const m = colonyMarks(v).find(q => px >= q.x && py >= q.y && px < q.x + q.w && py < q.y + q.h);
    return m ? m.o : null;
  }
  function drawColonyPanel() {
    const X = mapW(), side = sprite(D.side_panel.sprite.file, D.side_panel.sprite.index);
    if (side) {
      uiPut(side, X, 0);
      for (let y = side.h; y < uiCanvasWH()[1]; y += 6) uiPut(subSprite(side, 0, side.h - 6, side.w, 6), X, y);
      uiEdgeFill(X + side.w);
    }
    for (const w of D.widgets) {
      if (w.name === "orders") continue;
      const lit = ["back", "help", "prev", "next"].includes(w.name);
      uiWidget(w, X, 0, { disabled: !lit, onClick: w.name === "help" ? () => Help.open(() => Help.rec("world_map"), 1) : null, name: "" });
    }
    UIX.hits.push([X, 0, UIX.W - X, UIX.H, null, ""]);
    const p = colony.pick;
    box(Options.text(62, p ? 38 : 37), X + 0x12, 0x17A, F("9LTBK"), 0xDC);
    if (!p) return;
    box(p.name, X + 0x10, 0x41, F("11C"), 0x97, { center: true, lines: 1 });
    uiText(p.text || "", X + 0x14, 0xB9, F("9LTBK"), { width: 0xA0 });      // paragraph_draw (wrapped lines keep the space)
    const bx = X + 186 - 0x23, by = 0x172, hov = uiHover(bx, by, 24, 24);   // screen width - 0x23 beside a 186-px panel
    uiPut(sprite("Zeus_Interface", 268 + (hov ? 1 : 0)), bx, by);
    UIX.hits.push([bx, by, 24, 24, () => { const f = colony.onPick, n = p.n; f(n); }, "OK"]);
  }
  function colonyChoice(options, onPick) {
    load();
    refresh(true);
    open = true; dialog = null; sel = null; zf = 1; scroll = [0, 0];
    colony = { options, pick: null, onPick };
  }

  const armyUp = () => !!(window.MilPanel && MilPanel.armyOpen && MilPanel.armyOpen());   // screen 0x21: none
  function cityAt(x, y) {
    const v = view(), px = (x - v.mx) / v.k, py = (y - v.oy) / v.k;      // picture px (marker origin)
    let best = null, bd = 30;                   // FUN_00407360: icon rect + 8 px, nearest centre (Chebyshev < 30)
    for (const c of W.cities) {
      if (!c.map || !c.shown) continue;
      const [l, t, w, h] = iconRect(c);
      if (px < l - 8 || px >= l + w + 8 || py < t - 8 || py >= t + h + 8) continue;
      const d = Math.max(Math.abs(px - (l + Math.trunc(w / 2))), Math.abs(py - (t + Math.trunc(h / 2))));
      if (d < bd) { bd = d; best = c.id; }
    }
    return best;
  }

  return { ensure: () => { if (!D) load(); }, itemName, toggle, close, isOpen, holdsPopups, draw, down, refresh, colonyChoice, get colony() { return colony; }, get data() { return W; }, get conf() { return D; }, get overflow() { return overflow; }, get scroll() { return scroll; }, view: () => D && view(), zoomBy, get zoom() { return zf; }, set zoom(z) { zf = z; }, get dialogRect() { return dialog ? dlgRect : null; }, select: id => { sel = id; }, get selected() { return sel; },
           openDialog: (kind, extra) => { dialog = kind ? { kind, ...extra } : null; },
           strikeOpen: row => { const c = city(sel); if (c) strikeOpen(c, row); }, dialog: () => dialog };
})();

window.WorldMap = WorldMap;                    // the ui.js hooks test window.WorldMap (a top-level const is not a window property)
