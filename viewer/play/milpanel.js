// The exe's military screens (docs/play/military.md "The exe's military screens"):
// - screen 0x48, the company panel (panel_overlay_draw 0x00525280 + sidebar_draw_48 0x00525630): replaces the control
//   panel while a company is selected (a click on its icon on the military page 0x00516A50, or on one of its soldiers
//   or its standard on the map 0x00409150; Shift adds/removes): SPR_SIDE_MIL_PANEL, the minimap, the status box
//   (hover line, status 51:18..24), six buttons (centre, rotate, muster / send home, defensive / offensive / special:
//   handler 0x00405F70), the info box (FUN_00524CA0: name 138:banner, "@N Rabble", morale, the flag) or, with several
//   selected, their names (0x00640480); the magnifier opens the military advisor; a right click closes it;
// - screen 0x20, the trireme panel (sidebar_draw_20 0x00525C10): the same frame with the naval buttons (centre,
//   repair, crew home / call, defend, attack all, patrol), its status 184:N (FUN_005708D0) and hull condition;
// - screen 0x21, the army dialog "Enlist Forces" (FUN_005BBB60 / FUN_005BE0E0) for a raid or conquest from the world
//   map: horsemen and hoplite companies, the navy (sea routes only), Cancel / Enlist All / Clear All / Dispatch, the
//   plunder choice for a raid.
// Data: /military.json (Military.data: companies, navy), texts 51/138/184/283/5 in data/play/military.json.
"use strict";

const MilPanel = (() => {
  const T = (g, i) => { const t = MAP.military && MAP.military.texts && MAP.military.texts[String(g)]; return (t && t[i]) || ""; };
  const iface = (name, k = 0) => groupSprite("Zeus_Interface", name, k);
  const MODE_SPR = { rabble: ["SPR_LAND_DEF_ROCK", "SPR_LAND_OFF_ROCK", "SPR_LAND_SPEC_ROCK"],
                     hoplite: ["SPR_LAND_DEF_HOPLITE", "SPR_LAND_OFF_HOPLITE", "SPR_LAND_SPEC_HOPLITE"],
                     horseman: ["SPR_LAND_DEF_HORSE", "SPR_LAND_OFF_HORSE", "SPR_LAND_SPEC_HORSE"],
                     mixed: ["SPR_LAND_DEF_GEN", "SPR_LAND_OFF_GEN", "SPR_LAND_SPEC_GEN"] };
  const TYPE_WORD = { rabble: 34, hoplite: 35, horseman: 36 };
  let sel = [], ship = null, hoverId = -1, pressed = { i: -1, t: 0 }, army = null, scroll = 0;

  // ---- selection ----------------------------------------------------------------------------------------
  const M = () => (window.Military && Military.data) || null;
  const comp = slot => { const d = M(); return d && (d.companies || []).find(c => c.slot === slot); };
  function select(slot, add = false) {           // FUN_00524930 / 0x005248D0 (Shift toggles; at most 20)
    ship = null;
    if (!slot) { sel = []; if (window.Military) Military.select(0); return; }
    if (add) {
      sel = sel.includes(slot) ? sel.filter(s => s !== slot) : sel.length < 20 ? [...sel, slot] : sel;
    } else sel = [slot];
    if (window.Military) Military.select(sel[0] || 0);
  }
  let ships = [], box = null, groups = [null, null, null, null, null];
  function selectShip(id, add = false) {          // FUN_004092A0 / 0x005249E0 (Shift toggles; at most 20)
    sel = [];
    if (add) ships = ships.includes(id) ? ships.filter(s => s !== id) : ships.length < 20 ? [...ships, id] : ships;
    else ships = id ? [id] : [];
    ship = ships[0] || null;
    if (window.Military) Military.select(0);
  }
  const mode = () => (ship ? 0x20 : sel.length && window.Military && Military.selected ? 0x48 : 0);
  function close() { sel = []; ship = null; ships = []; scroll = 0; box = null; if (window.Military) Military.select(0); }

  // ---- the selection box (FUN_00433380 start, FUN_00433400 drawn in white 0xFFFF, FUN_00433A60 valid: top below
  // y 29, inside the city view, wider and taller than 2 px; FUN_00433700 select). Its corners are the screen points
  // of the tiles under the mouse (FUN_0056BF20, minus elevation x 30), so it steps by half tiles and stays on the
  // map when the view scrolls (the start tile is kept). 0x48 -> every company with a soldier (types 0xB..0xE) on
  // a tile in the box, except an event company that is recalled (+0x94, +0x78, +0x98); 0x20 -> every trireme in it
  const tpt = t => {                               // a tile's screen point, interface px (centre of its diamond)
    const el = (T && T.elev && T.elev[t[1] * N + t[0]]) || 0;
    return [(tileX(t[0], t[1]) + 29 - cam.x) * cam.zoom / UIX.scale, (tileY(t[0], t[1]) + 15 - el * 30 - cam.y) * cam.zoom / UIX.scale];
  };
  const mouseTile = e => typeof screenTile === "function" ? screenTile(e.clientX, e.clientY) : null;
  function boxStart(e) { const t = mouseTile(e); box = t ? { t0: t, t1: t } : null; }
  function boxMove(e) { const t = box && mouseTile(e); if (t) box.t1 = t; }
  function boxRect() {
    if (!box) return null;
    const [x0, y0] = tpt(box.t0), [x1, y1] = tpt(box.t1);
    return [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
  }
  function boxValid(r) { return r && r[1] > 29 && r[0] >= 0 && r[2] <= UIX.panelX && r[3] <= UIX.H && r[0] + 2 < r[2] && r[1] + 2 < r[3]; }
  function inBox(r, tx, ty) { const [sx, sy] = tpt([tx, ty]); return sx >= r[0] && sx <= r[2] && sy >= r[1] && sy <= r[3]; }
  function boxEnd(e) {
    boxMove(e);
    const r = boxRect();
    box = null;
    if (!boxValid(r)) return false;
    const d = M();
    if (!d) return true;
    const at = new Map();
    if (window.Scene && Scene.walkerHits) for (const h of Scene.walkerHits()) at.set(h[0], [h[6], h[7]]);
    if (mode() === 0x20) {
      const hit = (d.navy || []).filter(n => inBox(r, n.x, n.y)).map(n => n.id);
      ships = hit.slice(0, 20); ship = ships[0] || null;
      if (!ship) close();
      return true;
    }
    const hit = (d.companies || []).filter(c => !c.away && !(c.loan && c.recalled) && c.members > 0 &&
      (c.ids || []).some(i => at.has(i) && inBox(r, ...at.get(i))));
    sel = hit.map(c => c.slot).slice(0, 20); scroll = 0;
    if (window.Military) Military.select(sel[0] || 0);
    return true;
  }
  function drawBox() {
    const r = boxValid(boxRect()) && boxRect();
    if (!r || !UIX.red) return;
    const W = { sheet: UIX.red.sheet, x: 1, y: 0, w: 1, h: 1 };     // 0xFFFF
    const x0 = Math.round(r[0]), y0 = Math.round(r[1]), x1 = Math.round(r[2]), y1 = Math.round(r[3]);
    uiPut(W, x0, y0, 1, x1 - x0 + 1, 1); uiPut(W, x0, y1, 1, x1 - x0 + 1, 1);
    uiPut(W, x0, y0, 1, 1, y1 - y0 + 1); uiPut(W, x1, y0, 1, 1, y1 - y0 + 1);
  }

  // ---- company groups: Ctrl+1..5 stores the selection (FUN_00433AB0, in 0x48 / 0x20), Alt+1..5 recalls it
  // (FUN_00433B60, from the city screen too): dead ships / freed companies drop out; none left -> the previous
  // selection stays (none: back to the city screen)
  addEventListener("keydown", e => {
    const k = /^Digit([1-5])$/.exec(e.code);
    if (!k || !(e.ctrlKey || e.altKey) || e.metaKey) return;
    const i = +k[1] - 1, d = M();
    if (e.ctrlKey && !e.altKey) {
      if (!mode()) return;
      groups[i] = { mode: mode(), list: mode() === 0x20 ? ships.slice() : sel.slice() };
      e.preventDefault();
    } else if (e.altKey && groups[i] && d) {
      const gp = groups[i];
      if (gp.mode === 0x20) {
        const live = gp.list.filter(id => (d.navy || []).some(n => n.id === id));
        if (live.length) { sel = []; ships = live; ship = live[0]; if (window.Military) Military.select(0); }
      } else {
        const live = gp.list.filter(s => comp(s));
        if (live.length) { ships = []; ship = null; sel = live; if (window.Military) Military.select(live[0]); }
      }
      e.preventDefault();
    }
  });

  function centre(x, y) {                          // 0x0044A7D0: the view centred on a tile
    if (typeof cam === "undefined") return;
    cam.x = tileX(x, y) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
    cam.y = tileY(x, y) - innerHeight / 2 / cam.zoom;
  }
  const send = (cmds) => sendCommands(cmds, { sound: false }).then(() => window.Military && Military.refresh());

  // ---- a 69 x 47 button with the exe's four looks (+0 normal, +1 hover, +2 pressed, +3 disabled) --------------
  function button(name, x, y, id, onClick, { down = false, disabled = false } = {}) {
    const hov = !disabled && uiHover(x, y, 69, 47);
    if (hov) hoverId = id;
    const flash = pressed.i === id && performance.now() - pressed.t < 300;   // +0x19 = 0x14 after a click
    uiPut(iface(name, disabled ? 3 : down || flash ? 2 : hov ? 1 : 0), x, y);
    UIX.hits.push([x, y, 69, 47, disabled ? null : () => { pressed = { i: id, t: performance.now() }; onClick(); }, ""]);
  }

  // ---- screen 0x48 --------------------------------------------------------------------------------------
  function drawCompanies(X) {
    const d = M();
    const cs = sel.map(comp).filter(Boolean);
    if (!cs.length) { close(); return; }
    const c0 = cs[0], one = cs.length === 1;
    const classes = new Set(cs.map(c => c.type));
    const spr = classes.size < 2 ? MODE_SPR[c0.type] || MODE_SPR.horseman : MODE_SPR.mixed;
    const auto = d && d.auto_defend;
    hoverId = -1;
    const home = cs.filter(c => !c.mob).length, mob = cs.length - home;
    const muster = mob <= home;
    const pos = c => (c.mob ? c.dest : c.home) || c.dest;
    const act = (fn) => () => { if (!auto) fn(); };
    button("SPR_LAND_CENTER", X + 23, 203, 0x14, () => { const p = pos(c0); if (p) centre(p[0], p[1]); }, { disabled: !one });
    button(c0.layout === 2 || c0.layout === 12 || c0.layout === 14 ? "SPR_LAND_ROTATE2" : "SPR_LAND_ROTATE1", X + 23, 255,
           0x15, act(() => { send(cs.map(c => `rotate ${c.slot}`)); if (window.audio && audio.sfxNamed) audio.sfxNamed("cohort1"); }));
    button(muster ? "SPR_LAND_MUSTER" : "SPR_TAG_SEND_HOME", X + 23, 307, 0x16, act(() => {
      if (muster) send(cs.filter(c => !c.mob).map((c, k) => `mobilize ${c.slot}${c0.dest && c.slot !== c0.slot ? ` ${c0.dest[0]} ${c0.dest[1]}` : ""}`));
      else send(cs.filter(c => c.mob).map(c => `return ${c.slot}`));
    }));
    ["hold", "attack", "special"].forEach((m, i) => button(spr[i], X + 98, 203 + 52 * i, 0x17 + i,
      act(() => send(cs.map(c => `mode ${c.slot} ${m}`))), { down: (c0.mode || 0) === i }));
    // status box: the hover line (51:70..78) and the first company's status (51:18..24)
    uiPut(iface("SPR_LAND_STATUS", 0), X + 23, 147);
    const plural = cs.length > 1;
    const HOVER = { 0x14: one ? 70 : -1, 0x15: plural ? 76 : 71, 0x16: muster ? (plural ? 77 : 72) : 78, 0x17: 73, 0x18: 74,
                    0x19: 75, 200: 85 };
    if (hoverId >= 0 && HOVER[hoverId] >= 0) uiText(T(51, HOVER[hoverId]), X + 23, 156, "SPR_FONTS_9DKBU", { center: 140 });
    uiText(T(51, c0.status != null ? c0.status : 18), X + 23, 179, "SPR_FONTS_11C2", { center: 140 });
    // info box
    uiFrame("plain", X + 14, 360, 10, 7);
    const x0 = X + 28, y0 = 360;
    if (auto) {
      const lines = window.ZText ? ZText.wrap("SPR_FONTS_11CB", T(138, 68), 142) : [T(138, 68)];
      lines.forEach((ln, k) => uiText(ln, x0, y0 + 10 + 16 * k, "SPR_FONTS_11CB", { center: 142 }));
    } else if (one) {
      uiText(T(138, c0.banner || 0), x0, y0 + 10, "SPR_FONTS_11CB", { center: 142 });
      const num = window.ZText ? ZText.numberText(c0.members, "@", " ") : `${c0.members} `;
      uiText(num + T(138, TYPE_WORD[c0.type] || 35), x0 - 6, y0 + 25, "SPR_FONTS_11CB");
      uiText(`${T(138, 37)} ${T(138, 38 + Math.min(20, Math.floor((c0.morale || 0) / 5)))}`, x0, y0 + 40, "SPR_FONTS_11CB");
      const anim = Math.floor(performance.now() / 50) % 12;          // the flag waves while selected
      const flag = c0.loan ? groupSprite("Zeus_General", "SPR_FLAG_LOAN", anim >> 1)
        : groupSprite("Zeus_General", "SPR_FLAG_COMPANIES", (c0.banner || 0) * 7 + (anim >> 1));
      if (flag) uiPut(flag, x0 + 47, y0 + 60);
    } else nameRows(X, cs, c => T(138, c.banner || 0), c => { if (UIX.shift) select(c.slot, true); else select(c.slot); });
    magnifier(X);
  }

  // several selected (companies: 0x0057xxxx info box; triremes: FUN_005258D0): their names in the rows of
  // 0x00640480 (x 18..160, y 335 + 20 i, drawn at +0x26), centred, hovered 11C2 else 11CB; past 5: 3 rows and
  // Prev / Next (138:66 / 67, rows 4 and 5 at x + 8) scrolling by 3
  function nameRows(X, items, nameOf, onClick) {
    const n = items.length, rows = n <= 5 ? n : 3;
    if (n > 5) scroll = Math.max(0, Math.min(n - 3, scroll)); else scroll = 0;
    for (let i = 0; i < rows; i++) {
      const c = items[scroll + i], hx = X + 18, hy = 335 + 20 * i + 30;
      const hov = uiHover(hx, hy, 142, 20);
      uiText(nameOf(c), X + 18, 373 + 20 * i, hov ? "SPR_FONTS_11C2" : "SPR_FONTS_11CB", { center: 142 });
      UIX.hits.push([hx, hy, 142, 20, () => onClick(c), ""]);
    }
    if (n > 5) {
      if (scroll > 0) { uiText(T(138, 66), X + 26, 433, "SPR_FONTS_11CB"); UIX.hits.push([X + 18, 425, 142, 20, () => { scroll -= 3; }, ""]); }
      if (scroll !== n - 3) { uiText(T(138, 67), X + 26, 453, "SPR_FONTS_11CB"); UIX.hits.push([X + 18, 445, 142, 20, () => { scroll += 3; }, ""]); }
    }
  }

  function magnifier(X) {                          // SPR_MAG_GLASS: the military advisor (0x00408C00)
    const hov = uiHover(X + 157, 455, 18, 18);
    if (hov) hoverId = 200;
    uiPut(iface("SPR_MAG_GLASS", hov ? 1 : 0), X + 157, 455);
    UIX.hits.push([X + 157, 455, 18, 18, () => { close(); if (window.Advisors) Advisors.open(2); }, ""]);
  }

  // ---- screen 0x20: a trireme -------------------------------------------------------------------------------
  const SHIP_STATUS = { 6: 36, 0x14: 39, 0x15: 42, 0x16: 43, 0x1A: 43, 0x1B: 43, 0x17: 40, 0x18: 41, 0x19: 44, 0x1C: 45, 0x1D: 46 };
  function drawShip(X) {
    const d = M(), w = d && (d.navy || []).find(n => n.id === ship);
    if (!w) { close(); return; }
    hoverId = -1;
    const auto = d.auto_defend, a = w.mode != null ? w.mode : w.act;   // moving (0x19): its order (+0x34)
    // sidebar_draw_20 0x00525C10: enabled / pressed per button (table 0x00640390) and the muster picture
    let en = [1, 1, 1, 1, 1, 1], down = [0, 0, 0, 0, 0, 0], muster = "SPR_NAVAL_SEND_HOME";
    if (auto || (a === 0x13 && w.hull < 16)) { en = [1, 0, 0, 0, 0, 0]; muster = "SPR_LAND_MUSTER"; }   // 0x255
    else if (a === 0x18) { en = [1, 0, 1, 0, 0, 0]; muster = "SPR_LAND_MUSTER"; }                       // crew home
    else {
      en[0] = ships.length < 2 ? 1 : 0;              // centre: one trireme only
      if (a === 0x13) down[1] = 1; else if (a === 0x14) down[3] = 1; else if (a === 0x1A) down[4] = 1;
      else if (a === 0x15) down[5] = 1; else if (a === 0x17) muster = "SPR_NAVAL_MUSTER";            // 0x241
    }
    if (w.wharf && w.staff < 50 && w.act !== 0x18) en = [0, w.workers > 0 ? 1 : 0, w.workers > 0 ? 1 : 0, 0, 0, 0];
    const order = (o) => () => send(ships.map(id => `trireme ${id} ${o}`));   // every selected trireme
    const crewOff = a === 0x17 || a === 0x18;
    button("SPR_NAVAL_CENTER", X + 23, 203, 48, () => centre(w.x, w.y), { disabled: !en[0] });
    button("SPR_NAVAL_REPAIR", X + 23, 255, 49, order("repair"), { disabled: !en[1], down: down[1] });
    button(muster, X + 23, 307, crewOff ? 54 : 53, order("crewpanel"), { disabled: !en[2] });
    button("SPR_NAVAL_DEFEND", X + 98, 203, 50, order("hold"), { down: down[3], disabled: !en[3] });
    button("SPR_NAVAL_ATTACK_ALL", X + 98, 255, 51, order("hunt"), { down: down[4], disabled: !en[4] });
    button("SPR_NAVAL_PATROL", X + 98, 307, 52, order("patrol"), { down: down[5], disabled: !en[5] });
    uiPut(iface("SPR_NAVAL_STATUS", 0), X + 23, 147);
    if (hoverId >= 0) uiText(T(184, hoverId), X + 23, 156, "SPR_FONTS_9DKBU", { center: 140 });
    const st = w.act === 0x13 ? (w.crew < 50 ? 47 : w.label === 38 ? 37 : 38) : SHIP_STATUS[w.act];
    if (st) uiText(T(184, st), X + 23, 179, "SPR_FONTS_11C2", { center: 140 });
    uiFrame("plain", X + 14, 360, 10, 7);
    const x0 = X + 28, y0 = 360;                   // FUN_005258D0(panelX + 0x1C, 0x168): centred in 0x8C
    if (auto) {                                    // auto-defend: 138:68 as a paragraph at y0 + 10
      const lines = window.ZText ? ZText.wrap("SPR_FONTS_11CB", T(138, 68), 142) : [T(138, 68)];
      lines.forEach((ln, k) => uiText(ln, x0, y0 + 10 + 16 * k, "SPR_FONTS_11CB", { center: 142 }));
    } else if (ships.length > 1) {
      const live = ships.map(id => (d.navy || []).find(n => n.id === id)).filter(Boolean);
      nameRows(X, live, n => T(269, n.name || 0), n => selectShip(n.id, UIX.shift));
    } else {
      uiText(T(269, w.name || 0), x0, y0 + 7, "SPR_FONTS_11CB", { center: 140 });     // figure_name_group: 269
      uiText(T(184, 2), x0, y0 + 20, "SPR_FONTS_11CB", { center: 140 });
      const hullWord = 3 + Math.max(0, Math.min(4, (w.hull_text || 49) - 49));
      uiText(T(184, hullWord), x0, y0 + 38, hullWord === 7 ? "SPR_FONTS_11C3" : "SPR_FONTS_11C2", { center: 140 });
    }
    magnifier(X);
  }

  function draw(X) {
    uiPut(iface("SPR_SIDE_MIL_PANEL", 0), X, 0);
    if (typeof drawMinimap === "function") drawMinimap(X + 25, 28, 142, 109);
    if (mode() === 0x20) drawShip(X); else drawCompanies(X);
    drawBox();
  }

  // a left click on the map in 0x48: a company's soldier or standard selects it (Shift toggles); a trireme opens
  // 0x20; else a move order for the selected companies (FUN_00406290) or the trireme (FUN_004093E0)
  function mapClick(e, t) {
    const d = M();
    if (!d || !t) return false;
    const at = (p) => p && Math.abs(p[0] - t[0]) <= 0 && Math.abs(p[1] - t[1]) <= 0;
    const s = (typeof S !== "undefined" && S && S.walkers) || [];
    if (window.Scene && Scene.walkerHits) {
      const wx = cam.x + e.clientX / cam.zoom, wy = cam.y + e.clientY / cam.zoom;
      for (const h of Scene.walkerHits()) {
        if (!(wx >= h[1] && wy >= h[2] && wx < h[1] + h[3] && wy < h[2] + h[4])) continue;
        const tri = (d.navy || []).find(n => n.id === h[0]);
        if (tri) { selectShip(tri.id, e.shiftKey && mode() === 0x20); return true; }
        const c = (d.companies || []).find(c => (c.ids || []).includes(h[0]));
        if (c && !c.away) { select(c.slot, e.shiftKey && mode() === 0x48); return true; }
      }
    }
    const c = (d.companies || []).find(c => c.mob && at(c.dest));
    if (c) { select(c.slot, e.shiftKey && mode() === 0x48); return true; }
    if (mode() === 0x20) { send(ships.map(id => `trireme ${id} ${t[0]} ${t[1]}`)); return true; }
    if (mode() === 0x48 && !e.shiftKey) {
      if (d.auto_defend) return true;
      send(sel.map((s, k) => `${comp(s) && comp(s).mob ? "move" : "mobilize"} ${s} ${t[0]} ${t[1]}`));
      if (window.audio && audio.sfxNamed) audio.sfxNamed("cohort5");
      return true;
    }
    return false;
  }

  // ---- screen 0x21: the army dialog ------------------------------------------------------------------------
  // allies: the cities with a strike request code 3 (city_can_request(0x1B)); heroes: up to 3 present (/heroes.json)
  // kind "quest" (a god's quest, event type 4; quest = {id, god, hero} from /heroes.json quests): army_dialog_build
  // 0x005BBB60 clears +0x164 (companies, mythical warriors: listed, not toggleable, FUN_005BB900), +0x163 (allies: box
  // not drawn) and +0x160 (navy: 283:17); the title 283:25 "Choose Forces for [god] Quest" ([god] = 157:god of +0x60; the token table not read)
  // kind "request" (a scenario request for troops, type 1 item 24; req = its state.json events row): army_dialog_build
  // clears +0x163 (no allies box: flag 0x4000 and player expeditions only) and for kind 7 (slay a monster) +0x164 and
  // +0x160 as for a quest; the title 283:3 "Choose forces to defend [city_name]" or kind 2 283:4 "... help
  // [city_name] attack [rival_city_name]" (FUN_005BC400)
  function openArmy(city, kind, route, sells, allies, quest, req) {
    army = { city, kind, route, sells: sells || [], allies: kind === "quest" || kind === "request" ? [] : allies || [], heroes: [], plunder: null,
             ally: null, on: new Set(), confirm: null, popup: false, ascroll: 0, quest: quest || null, req: req || null };   // nothing enlisted
    fetch("/heroes.json").then(r => r.json()).then(h => {
      if (army) army.heroes = (h.heroes || []).filter(x => x.present).slice(0, 3);
    }).catch(() => { });
  }
  function drawArmy() {
    if (!army) return;
    const d = M() || {};
    const ox = Math.trunc((UIX.W - 640) / 2), oy = Math.trunc((UIX.H - 480) / 2), fx = ox - 30, fy = oy - 30;
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiFrame("titled", fx, fy, 37, 34);
    uiText(T(283, 0), ox + 4, fy + 16, "SPR_FONTS_22C");
    const req = army.kind === "request" ? army.req : null;
    const quest = army.kind === "quest" || !!(req && req.kind === 7);     // +0x164 / +0x160 cleared
    const noAllies = army.kind === "quest" || !!req;                      // +0x163 cleared
    const godName = army.quest ? army.quest.god_name || "" : "";   // 157:god (/heroes.json quests; a kind-7 request has none, bug 469)
    uiText(req ? T(283, req.kind === 2 ? 4 : 3).replace("[city_name]", army.city).replace("[rival_city_name]", req.rival || "")
           : quest ? T(283, 25).replace("[god]", godName) : T(283, army.kind === "raid" ? 2 : 1).replace("[city_name]", army.city),
           ox + 4, fy + 51, "SPR_FONTS_11C");
    const comps = (d.companies || []).filter(c => c.slot <= 20 && (c.type === "horseman" || c.type === "hoplite") && c.members > 0);
    const horse = comps.filter(c => c.type === "horseman"), hop = comps.filter(c => c.type === "hoplite");
    const lx = ox + 4, rx = ox + 290;
    const nh = horse.length || (hop.length < 20 ? 1 : 0);
    const hh = Math.round((18 * nh + 33) / 16) * 16, ph = Math.floor((393 - 18 * nh) / 16) * 16;   // oracle: 51 -> 48
    uiText(T(283, 5), lx, fy + 84 - 18, "SPR_FONTS_11C", { center: 272 });
    uiText(T(283, 6), rx, fy + 84 - 18, "SPR_FONTS_11C", { center: 240 });
    const box = (x, y, w, h, title, rows, empty) => {
      uiFrame("plain", x, y, w / 16, Math.max(1, h / 16));
      uiText(title, x + 9, y + 11, "SPR_FONTS_9DKBU");
      if (!rows.length) uiText(T(283, 12), x + 9, y + 29, "SPR_FONTS_9DKBU");
      rows.forEach((r, i) => r(x, y + 18 + 18 * i + (empty ? 0 : 0)));
    };
    const compRow = (c) => (x, y) => {
      const key = "c" + c.slot, on = army.on.has(key), ok = !c.away && !quest;    // FUN_005BB900: event type != 4
      uiPut(iface("SPR_MIL_ADVISOR_FLAGS", c.banner || 0), x + 2, y + 1);
      uiPut(iface("SPR_MIL_SM_ADVISOR_TYPES", c.type === "horseman" ? 0 : 1), x + 32, y);
      const f = c.away ? "SPR_FONTS_9DKYEL" : on ? "SPR_FONTS_9DKBU" : "SPR_FONTS_9B";
      uiText(T(138, c.banner || 0), x + 60, y + 5, f);
      uiText(window.ZText ? ZText.numberText(c.members, "@", "") : String(c.members), x + 173, y + 5, f);
      // FUN_005BC400: 283:16 when abroad (+0x82 >= 0), 283:13 when enlisted, nothing at home
      if (c.away || on) uiText(c.away ? T(283, 16) : T(283, 13), x + 201, y + 5, f);
      if (on) uiPut(iface("SPR_ENLIST_GLOBE", 0), x + 257, y);
      if (ok) UIX.hits.push([x, y, 269, 17, () => { on ? army.on.delete(key) : army.on.add(key); }, ""]);
    };
    box(lx, fy + 84, 272, hh, T(283, 7), horse.map(compRow));
    box(lx, fy + 502 - ph, 272, ph, T(283, 14), hop.map(compRow));
    uiText(T(283, 11), lx + 166, fy + 84 + 11, "SPR_FONTS_9DKBU");
    uiText(T(283, 11), lx + 166, fy + 502 - ph + 11, "SPR_FONTS_9DKBU");
    const navy = d.navy || [];
    uiFrame("plain", rx, fy + 84, 15, 9);
    if (!navy.length) uiText(T(283, 12), rx + 9, fy + 84 + 29, "SPR_FONTS_9DKBU");
    navy.forEach((n, i) => {
      const y = fy + 84 + 18 * i + 8, key = "s" + n.id, on = army.on.has(key);
      const ok = army.route === "sea" && !quest && n.act !== 0xC && n.act !== 0xD && n.hull >= 26;   // +0x160
      uiPut(iface("SPR_MIL_SM_ADVISOR_TYPES", 3), rx + 8, y);
      const f = on ? "SPR_FONTS_9DKBU" : "SPR_FONTS_9B";
      uiText(T(51, n.hull_text || 49), rx + 34, y + 5, f);
      uiText(on ? T(283, 13) : n.hull < 26 ? T(283, 15) : T(51, n.label != null ? n.label : 33), rx + 163, y + 5, f);
      if (on) uiPut(iface("SPR_ENLIST_GLOBE", 0), rx + 223, y);
      if (ok) UIX.hits.push([rx, y, 240, 17, () => { on ? army.on.delete(key) : army.on.add(key); }, ""]);
    });
    if (army.route !== "sea" || quest) uiText(T(283, 17), rx + 9, fy + 84 + 126, "SPR_FONTS_9DKBU");
    // other forces (FUN_005BBB60): heroes (fy+258, 80 high), mythical warriors = sanctuary companies 31..34
    // (fy+340, 96), support from allies (fy+438, 64; raids and player expeditions)
    uiText(T(283, 8), rx, fy + 258 - 18, "SPR_FONTS_11C", { center: 240 });
    const toggle = (key) => () => { army.on.has(key) ? army.on.delete(key) : army.on.add(key); };
    uiFrame("plain", rx, fy + 258, 15, 5); uiText(T(283, 9), rx + 9, fy + 258 + 11, "SPR_FONTS_9DKBU");
    if (!army.heroes.length) uiText(T(283, 12), rx + 9, fy + 258 + 29, "SPR_FONTS_9DKBU");
    army.heroes.forEach((h, i) => {                // 185:hero at +34; away (+0x132 >= 0): 283:16 "Abroad" 9DKYEL
      const y = fy + 258 + 18 + 18 * i, key = "h" + h.id, on = army.on.has(key);
      const f = on ? "SPR_FONTS_9DKBU" : h.away ? "SPR_FONTS_9DKYEL" : "SPR_FONTS_9B";
      uiText(h.name, rx + 34, y + 5, f);
      if (on) { uiText(T(283, 13), rx + 163, y + 5, f); uiPut(iface("SPR_ENLIST_GLOBE", 0), rx + 223, y); }
      else if (h.away) uiText(T(283, 16), rx + 163, y + 5, f);
      if (!h.away) UIX.hits.push([rx, y, 240, 17, toggle(key), ""]);   // FUN_005BB9A0
    });
    uiFrame("plain", rx, fy + 340, 15, 6); uiText(T(283, 10), rx + 9, fy + 340 + 11, "SPR_FONTS_9DKBU");
    uiText(T(283, 11), rx + 136, fy + 340 + 11, "SPR_FONTS_9DKBU");
    const myth = (d.companies || []).filter(c => c.slot >= 31 && c.slot <= 34 && c.members > 0);
    if (!myth.length) uiText(T(283, 12), rx + 9, fy + 340 + 29, "SPR_FONTS_9DKBU");
    myth.forEach((c, i) => {
      const y = fy + 340 + 18 + 18 * i, key = "c" + c.slot, on = army.on.has(key), f = c.away ? "SPR_FONTS_9DKYEL" : on ? "SPR_FONTS_9DKBU" : "SPR_FONTS_9B";
      // FUN_005BC400: icon FUN_0051ABE0(slot, 1) (slots > 20: type 0xB -> 4, 0xC -> 5, 0xD -> 0), name 138:(+0x42) at
      // +0x22, members at +0x90, then 283:16 (abroad, +0x82 >= 0) or 283:13 (enlisted) at +0xA3, nothing at home
      uiPut(iface("SPR_MIL_SM_ADVISOR_TYPES", c.type === "hoplite" ? 5 : c.type === "rabble" ? 4 : 0), rx + 4, y);
      uiText(T(138, c.slot - 1), rx + 34, y + 5, f);
      uiText(window.ZText ? ZText.numberText(c.members, "@", "") : String(c.members), rx + 144, y + 5, f);
      if (c.away || on) uiText(c.away ? T(283, 16) : T(283, 13), rx + 163, y + 5, f);
      if (on) uiPut(iface("SPR_ENLIST_GLOBE", 0), rx + 223, y);
      if (!c.away && !quest) UIX.hits.push([rx, y, 240, 17, toggle(key), ""]);
    });
    if (!noAllies) { uiFrame("plain", rx, fy + 438, 15, 4); uiText(T(283, 24), rx + 9, fy + 438 + 11, "SPR_FONTS_9DKBU"); }   // +0x163
    if (!noAllies && !army.allies.length) uiText(T(283, 12), rx + 9, fy + 438 + 29, "SPR_FONTS_9DKBU");
    army.allies.slice(army.ascroll, army.ascroll + 2).forEach((name, i) => {
      const y = fy + 438 + 18 + 18 * i, on = army.ally === name, f = on ? "SPR_FONTS_9DKBU" : "SPR_FONTS_9B";
      uiText(name, rx + 34, y + 5, f);
      if (on) { uiText(T(283, 13), rx + 163, y + 5, f); uiPut(iface("SPR_ENLIST_GLOBE", 0), rx + 223, y); }
      UIX.hits.push([rx, y, 240, 17, () => { army.ally = on ? null : name; }, ""]);
    });
    if (army.allies.length > 2) {                  // arrows (0x005BB840)
      const ax = ox + 532;
      uiPut(sprite("Zeus_Interface", 127), ax, fy + 459); UIX.hits.push([ax, fy + 459, 20, 20, () => { army.ascroll = Math.max(0, army.ascroll - 1); }, ""]);
      uiPut(sprite("Zeus_Interface", 16), ax, fy + 480); UIX.hits.push([ax, fy + 480, 20, 20, () => { army.ascroll = Math.min(army.allies.length - 2, army.ascroll + 1); }, ""]);
    }
    // buttons: outline on hover, label centred (9LTBK)
    const btn = (x1, y1, x2, y2, label, fn) => {
      const x = ox + x1, y = oy + y1, w = x2 - x1, h = y2 - y1;
      if (window.Options && Options.rims) Options.rims(x, y, w, h, uiHover(x, y, w, h));
      uiText(label, x + 6, y + 6, "SPR_FONTS_9LTBK", { center: w });   // centred in w from x1+6 (oracle army-dialog)
      UIX.hits.push([x, y, w, h, fn, label]);
    };
    btn(5, 480, 125, 500, T(283, 18), () => { army = null; });
    btn(153, 480, 273, 500, T(283, 19), () => {        // every eligible row and the first ally
      if (!quest) for (const c of comps.concat(myth)) if (!c.away) army.on.add("c" + c.slot);
      if (army.route === "sea" && !quest) for (const n of navy) if (n.act !== 0xC && n.act !== 0xD && n.hull >= 26) army.on.add("s" + n.id);
      for (const h of army.heroes) if (!h.away) army.on.add("h" + h.id);
      if (army.allies.length && !army.ally) army.ally = army.allies[0];
    });
    btn(290, 480, 410, 500, T(283, 20), () => { army.on.clear(); army.ally = null; });
    btn(409, 480, 529, 500, T(283, 21), () => {
      if (army.kind === "quest") return questDispatch();
      if (req && req.kind === 7) return monsterDispatch();
      if (!army.on.size) { army.confirm = 0xC; return; }
      army.confirm = req ? (req.kind === 2 ? 0x4C : 0xE) : 0xAF;      // army_dialog_dispatch_btn 0x005BDE70
    });
    const GOOD = g => (window.WorldMap && WorldMap.itemName ? WorldMap.itemName(g) : g.replace(/_/g, " "));
    if (army.kind === "raid") {
      uiText(T(283, 22), ox + 346 + 6, oy + 5 - 20, "SPR_FONTS_11C", { center: 142 });   // oracle: 1 px right of w=140
      btn(346, 5, 486, 25, army.plunder ? GOOD(army.plunder) : T(283, 23), () => { army.popup = true; });
    }
    if (army.popup) {                              // screen 0x0F (FUN_005BEFE0): the goods the city can be asked
      // for (its sells, drachmas) and "Any"; a titled frame 13 x n+2 cells at (ox+135, oy) (oracle army-dialog
      // plunder.bmp), rows 20 px from y+14, names centred (11C)
      const goods = [...army.sells, "drachmas", null], px = ox + 135, py = oy;
      uiFlushText();
      UIX.hits.push([0, 0, UIX.W, UIX.H, () => { army.popup = false; }, ""]);
      uiFrame("titled", px, py, 13, goods.length + 2);
      goods.forEach((gd, i) => {
        const y = py + 14 + 20 * i, hov = uiHover(px + 5, y, 200, 18);
        uiText(gd ? GOOD(gd) : T(283, 23), px, y, hov ? "SPR_FONTS_11C2" : "SPR_FONTS_11C", { center: 206 });   // oracle plunder.bmp: 0 px
        UIX.hits.push([px + 5, y, 200, 18, () => { army.plunder = gd; army.popup = false; }, ""]);
      });
    }
    if (army.confirm != null) {                    // screen 0x3F (FUN_00432380 at the 640 x 480 origin + 0x50)
      uiFlushText();                              // the dialog's texts under the popup
      const ok = [0xAF, 0xE, 0x4C].includes(army.confirm);
      const yes = () => {
        const slots = [...army.on].filter(k => k[0] === "c").map(k => k.slice(1));
        const ships = [...army.on].filter(k => k[0] === "s").map(k => k.slice(1));
        const heroes = [...army.on].filter(k => k[0] === "h").map(k => k.slice(1));
        const tail = ` companies ${slots.join(",") || "none"} ships ${ships.join(",") || "none"}`
          + `${heroes.length ? " heroes " + heroes.join(",") : ""}`;
        const line = army.req ? `answer ${army.req.id} dispatch${tail}`
          : `${army.kind} ${army.city}${army.kind === "raid" && army.plunder ? " " + army.plunder : ""}`
            + `${army.ally ? " with " + army.ally : ""}${tail}`;
        army = null;
        sendCommands([line], { sound: false }).then(() => { if (window.WorldMap) WorldMap.refresh(true); if (window.Military) Military.refresh(); });
      };
      const vars = { city_nameA: army.city, city_nameB: army.req ? army.req.rival || "" : "" };
      // the refusals (0xC no companies, the quest's / monster's 0xA5 / 0xA9 / 0xB5 / 0xC1 / 0xC3 / 0xC5) have no button:
      // FUN_00432380(id, empty_function, 0) -> "Right-click to continue" (bugs.md 365)
      popup3F(army.confirm, ok ? yes : null, ok ? () => { army.confirm = null; } : null, vars);
    }
  }

  // Screen 0x3F (FUN_00432380, drawn by FUN_00431370; oracle 1F-strike strike_confirm 0 px): titled frame 30 x 10 at
  // the 640 x 480 origin + (0x50, 0x50); title 5:id 22C centred in 480 at y + 0x14; text 5:id+1 11C centred in 480 at
  // y + 0x3C (wider than 0x1A3: a paragraph 0x1A4 wide at x + 0x1E); buttons (FUN_004314C0, table 0x005EF938): OK
  // SPR_BUTTONS6 324 at (256, 100), cancel 328 at (192, 100) (two-button popups only), 34 x 34, + 1 hovered; no ok:
  // no button, 13:1 "Right-click to continue" instead (FUN_004314C0 with count 0).
  // vars: the text's [city_nameA] / [city_nameB] ...
  function popup3F(id, ok, cancel, vars = {}) {
    const cx = Math.trunc((UIX.W - 640) / 2) + 0x50, cy = Math.trunc((UIX.H - 480) / 2) + 0x50;
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiFrame("titled", cx, cy, 30, 10);
    let body = T(5, id + 1);
    for (const [k, v] of Object.entries(vars)) body = body.replace(`[${k}]`, v);
    uiText(T(5, id), cx, cy + 0x14, "SPR_FONTS_22C", { center: 480 });
    if (window.ZText && ZText.advance("SPR_FONTS_11C", body) > 0x1A3) uiText(body, cx + 0x1E, cy + 0x3C, "SPR_FONTS_11C", { width: 0x1A4 });
    else uiText(body, cx, cy + 0x3C, "SPR_FONTS_11C", { center: 480 });
    if (!ok) {                                    // no button (FUN_004314C0: count 0): 13:1 11C centred in 480 at y + 0x80
      uiText(T(13, 1), cx, cy + 0x80, "SPR_FONTS_11C", { center: 480 });
      return;
    }
    const bs = [[256, 324, ok, "OK"]];
    if (cancel) bs.push([192, 328, cancel, "Cancel"]);
    for (const [bx, img, fn, nm] of bs) {
      const hov = uiHover(cx + bx, cy + 100, 34, 34);
      uiPut(sprite("Zeus_Interface", img + (hov ? 1 : 0)), cx + bx, cy + 100);
      UIX.hits.push([cx + bx, cy + 100, 34, 34, fn, nm]);
    }
  }

  // Dispatch for a request to slay a monster (kind 7, FUN_005BDC70): more than one hero enlisted 5:0xC1, the monster's
  // hero (scenario_hero_of_monster_slot(+0x36)) not in the city 0xC3, not enlisted 0xC5; else army_dialog_dispatch
  // (no confirm)
  function monsterDispatch() {
    const enlisted = army.heroes.filter(h => army.on.has("h" + h.id)), want = army.req.hero;
    let id = -1;
    if (enlisted.length > 1) id = 0xC1;
    if (!army.heroes.some(h => h.id === want)) id = 0xC3;
    if (!enlisted.some(h => h.id === want)) id = 0xC5;
    if (id >= 0) { army.confirm = id; return; }
    const line = `answer ${army.req.id} dispatch companies none ships none heroes ${want}`;
    army = null;
    sendCommands([line], { sound: false }).then(() => { if (window.Military) Military.refresh(); });
  }

  // Dispatch for a quest (army_dialog_dispatch_btn 0x005BDE70 -> FUN_005BDAD0(0)): the quest needs a hero (item 0x1A
  // among +6/+8/+0xA, FUN_004691E0; open-play quests do); more than one hero enlisted -> 5:0xB5, its hero (the slot +0x36's,
  // scenario_hero_of_monster_slot) not in the city -> 0xA5, its hero not enlisted -> 0xA9 (one OK popup, screen 0x3F);
  // else straight to army_dialog_dispatch (no confirm): FUN_0046DA70 state 6 + expedition_send_forces (sim `dispatch`)
  function questDispatch() {
    const enlisted = army.heroes.filter(h => army.on.has("h" + h.id)), want = army.quest.hero;
    const right = enlisted.some(h => h.id === want), present = army.heroes.some(h => h.id === want);
    let id = -1;
    if (enlisted.length > 1) id = 0xB5;
    if (!present) id = 0xA5;
    if (!right) id = 0xA9;
    if (id >= 0) { army.confirm = id; return; }
    const h = army.heroes.find(x => x.id === want);
    army = null;
    sendCommands([`dispatch ${h.name}`], { sound: false }).then(() => { if (window.Military) Military.refresh(); });
  }

  function rightClick() {
    if (army) { if (army.popup) army.popup = false; else if (army.confirm != null) army.confirm = null; else army = null; return true; }
    if (mode()) { close(); return true; }
    return false;
  }

  return { popup3F, select, selectShip, close, mode, draw, mapClick, openArmy, drawArmy, rightClick, boxStart, boxMove, boxEnd, boxRect: () => { const r = boxRect(); return boxValid(r) ? r : null; },
           get ship() { return ship; }, get ships() { return ships.slice(); },
           armyOpen: () => !!army, get selection() { return sel.slice(); } };
})();
window.MilPanel = MilPanel;
