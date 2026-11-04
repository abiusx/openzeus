// Control-panel page contents: the info box under each page's overlay buttons (docs/play/pages.md).
// The exe's page functions (FUN_00517000 switch: 0x00518B20 population .. 0x005B6F00 overview) laid out by
// hand here; strings and level tables from data/play/pages.json (tools/play_pages.py). Presentation only:
// values come from state.json (city, reports, buildings); clicks send the same script commands as the
// rest of play mode (tax N, wage N, stockpile GOOD on|off).
"use strict";

const ZPages = (() => {
  let D = null, RES = {};
  Promise.all([fetch("/data/play/pages.json").then(r => r.json()), fetch("/data/resources.json").then(r => r.json()).catch(() => [])])
    .then(([d, res]) => { D = d; for (const r of (Array.isArray(res) ? res : Object.values(res))) if (r && r.key) RES[r.key] = r.zeus_id; })
    .catch(e => console.error("pages:", e));

  const F = { 3: "11C2", 4: "11C3", 8: "9B", 10: "9LTBK", 13: "9DKBU", 14: "9DKYEL", 1: "11C", 0: "SMALL" };   // font ranks
  const str = (g, i) => (D && D.strings[g] && D.strings[g][i]) || "";
  const num = n => (window.ZText ? ZText.numberText(n) : " " + n + " ");

  // --- report helpers (sim/reports.py rows) ------------------------------------------------------
  function row(page, label) {
    const secs = S && S.reports && S.reports[page];
    for (const s of secs || []) for (const r of s.rows || []) if (r[0] === label) return r[1];
    return null;
  }
  function table(page, title) {
    for (const s of (S && S.reports && S.reports[page]) || []) if (s.title === title && s.table) return s.table;
    return null;
  }
  const firstInt = v => { const m = /-?\d+/.exec(String(v == null ? "" : v)); return m ? +m[0] : 0; };
  const paren = v => { const m = /\((?:≈)?(-?\d+)/.exec(String(v == null ? "" : v)); return m ? +m[1] : 0; };
  const houses = () => (S ? S.buildings.filter(b => b.kind === "house") : []);

  // --- drawing ------------------------------------------------------------------------------------
  let C = null;                                    // {X, Y}: panel left, n_overlays*20
  function text(s, x, y, font, w) { uiText(s, C.X + x, C.Y + y, F[font] || font, w ? { center: w } : {}); }
  function para(s, x, y, font, w) {                // paragraph_draw centred (0x005086E0): lines of 16 px
    const lines = window.ZText ? ZText.wrap(F[font], s, w) : [s];
    lines.forEach((ln, k) => uiText(ln, C.X + x, C.Y + y + 16 * k, F[font], { center: w }));
    return lines.length;
  }
  function paraLeft(s, x, y, font, w) {            // paragraph_draw (0x005090A0): left-aligned lines of 16 px (bugs.md 330)
    const lines = window.ZText ? ZText.wrap(F[font], s, w) : [s];
    lines.forEach((ln, k) => uiText(ln, C.X + x, C.Y + y + 16 * k, F[font]));
    return lines.length;
  }
  function sep(y) {                                // tile_row_draw(panelX+50, y, 8): SPR_MARBLE_BAR 0/1/2
    for (let k = 0; k < 8; k++) uiPut(groupSprite("Zeus_Interface", "SPR_MARBLE_BAR", k === 0 ? 0 : k === 7 ? 2 : 1), C.X + 50 + 16 * k, C.Y + y);
  }
  function arrows(y, onDown, onUp, what) {         // SPR_BUTTON_DOWN at +0x5F, SPR_BUTTON_UP at +0x77; hit 5 px higher (exe)
    [[0, "SPR_BUTTON_DOWN", onDown, "Lower " + what], [24, "SPR_BUTTON_UP", onUp, "Raise " + what]].forEach(([dx, g, fn, name]) => {
      const x = C.X + 0x5F + dx, yy = C.Y + y, hov = uiHover(x, yy - 5, 24, 24);
      uiPut(groupSprite("Zeus_Interface", g, hov && UIX.down ? 1 : 0), x, yy);
      UIX.hits.push([x, yy - 5, 24, 24, fn, name, true]);   // held: repeats (ui.js uiRepeat)
    });
  }
  // a setting shows the new value at once; the value the player picked is kept until the tab has the
  // snapshot the server recorded after applying it (S.seq; as build.js does for buildings)
  const PEND = {};
  const val = (key, actual) => {
    const p = PEND[key];
    if (p && (S.seq == null || S.seq < p.tick)) return p.v;
    delete PEND[key];
    return actual;
  };
  const send = (cmd, key, v) => {
    if (typeof sendCommands !== "function") return null;
    if (key) PEND[key] = { v, tick: Infinity };
    return Promise.resolve(sendCommands([cmd], { sound: !key })).then(t => {
      if (!key) return;
      if (t == null) delete PEND[key]; else if (PEND[key] && PEND[key].v === v) PEND[key].tick = t;
    });
  };
  const nearest = (vals, v) => vals.reduce((bi, x, i) => Math.abs(x - v) < Math.abs(vals[bi] - v) ? i : bi, 0);

  // --- pages ----------------------------------------------------------------------------------------
  function population() {                          // 0x00518B20
    const c = S.city;
    text(str(55, 8), 0x37, 0x44, 8, 120);
    text(num(Math.max(0, c.vacancies || 0)), 0x37, 0x4E, 3, 120);
    text(str(55, 9), 0x37, 0x64, 8, 120);
    const trend = String(row("population", "trend") || ""), arrived = firstInt((/\+(\d+)/.exec(trend) || [])[1]);
    const limited = String(row("population", "immigration limited by") || "none");
    const parts = c.sentiment_parts || {}, worst = Object.entries(parts).filter(([, v]) => v < 0).sort((a, b) => a[1] - b[1])[0];
    let H, second = null;
    if (arrived > 4) { H = 20; second = ["count", arrived, 10]; }
    else if ((c.vacancies || 0) < 1) { H = 20; second = ["limit", str(55, 13)]; }
    else if (/grow/.test(trend) && arrived > 0) { H = 20; second = ["count", arrived, arrived === 1 ? 11 : 10]; }
    else if (/shrink|leav/.test(trend) || (limited !== "none" && worst)) {
      H = 21;
      const cause = worst && { food: 16, unemployment: 15, taxes: 17, wages: 14, debt: 18 }[worst[0]];
      if (cause) second = ["limit", str(55, cause)];
    } else H = 22;
    sep(0x7C);
    para(str(55, H), 0x37, 0x84, 13, 120);
    sep(0xC0);
    if (second && second[0] === "count") { text(num(second[1]), 0x37, 0xC8, 3, 120); para(str(55, second[2]), 0x37, 0xD8, 8, 120); }
    else if (second) { const L = para(str(55, 12), 0x37, 0xC8, 13, 120); para(second[1], 0x37, 0xC8 + 16 * L, 14, 120); }
  }

  function husbandry() {                           // 0x005195B0
    const feeds = firstInt(row("husbandry", "production feeds")), pop = S.city.population || 1;
    let L = para(str(57, 1), 0x2D, 0x44, 8, 140);
    text(num(feeds), 0x2D, 0x44 + 16 * L, 3, 140);
    para(str(57, 2), 0x2D, 0x54 + 16 * L, 8, 140);
    const pct = feeds * 100 / pop;
    const [k, f] = pct > 150 ? [8, 13] : pct > 110 ? [7, 13] : pct > 95 ? [6, 8] : pct > 85 ? [5, 14] : pct > 70 ? [4, 14] : [3, 14];
    L = para(str(57, k), 0x2D, 0xA4, f, 140);
    const mig = String(row("population", "trend") || "");
    const t = /shrink|leav/.test(mig) ? 10 : /grow/.test(mig) && (S.city.vacancies || 0) > 0 ? 11 : 9;
    para(str(57, t), 0x2D, 0xA4 + 16 * L, 8, 140);
    sep(0xD2);
    L = para(str(57, 27), 0x2D, 0xDA, 13, 140);
    text(num(paren(row("husbandry", "food stored"))), 0x2D, 0xDA + 16 * L, 3, 140);
    para(str(57, 28), 0x2D, 0xEE + 16 * L, 13, 140);
  }

  function industry() {                            // 0x00518750
    const W = D.wage_levels.values, k = nearest(W, val("wage", S.city.wage));
    const wage = v => send(`wage ${v}`, "wage", v);
    arrows(0x61, () => wage(W[Math.max(0, k - 1)]), () => wage(W[Math.min(W.length - 1, k + 1)]), "wages");
    text(str(131, 1), 0x37, 0x44, 13, 128);
    text(str(285, k), 0x37, 0x55, 13, 128);
    para(`${str(50, 16)} ${paren(row("industry", "wage"))} dr`, 0x2D, 0x96, 13, 140);
    sep(0xBA);
    para(`${str(50, 12)} ${S.city.employed || 0}`, 0x46, 0xC2, 13, 96);
    const wf = S.city.workforce || 0, un = S.city.unemployed || 0, pct = wf ? Math.round(100 * un / wf) : 0;
    if (pct < 1) para(`${firstInt(row("industry", "jobs open"))} ${str(61, 13)}`, 0x46, 0xF4, 13, 94);
    else para(`${str(50, 13)} ${un} (${pct}%)`, 0x46, 0xF4, 13, 94);
  }

  function distribution() {                        // 0x00517F50: goods list, rows of 12 px from y 0x55 (not offset)
    const t = table("distribution", "Inventory");
    if (!t) return;
    // FUN_00517E30: the goods list without horses and chariots, as [-1 "Imports"] + the importing goods (trade state
    // 5), [-2 "Exports"] + the exporting ones (7), then the rest (9); a header only when its group has goods; at
    // most 18 rows. A marble bar under the last row of each traded group (0x5D + 12 i, tile_row_draw 0x0059F600)
    const ci = n => t.cols.indexOf(n), goods = t.rows.filter(r => r[0] !== "horses" && r[0] !== "chariot");
    const st = r => (ci("state") >= 0 ? +r[ci("state")] : 9) || 9, list = [];
    for (const [s, h] of [[5, -1], [7, -2], [9, 0]]) {
      const g = goods.filter(r => st(r) === s);
      if (h && g.length) list.push(h);
      list.push(...g);
    }
    const rows = list.slice(0, 18), X = UIX.panelX;
    rows.forEach((r, i) => {
      const y = 0x55 + 12 * i;
      if (r === -1 || r === -2) {
        uiText(str(130, r === -1 ? 17 : 18), X + 0x34, y, F[13]);
        if (r === -2) uiText(str(130, 13), X + 0x41 + ZText.draw(null, F[13], str(130, 18), 0, 0).cursor, y, F[14]);
        return;
      }
      const nx = rows[i + 1], s9 = st(r);
      if (s9 !== 9 && (nx == null || typeof nx === "number" || st(nx) !== s9))
        for (let k = 0; k < 8; k++) uiPut(groupSprite("Zeus_Interface", "SPR_MARBLE_BAR", k === 0 ? 0 : k === 7 ? 2 : 1), X + 0x32 + 16 * k, 0x5D + y - 0x55);
      const good = r[0], loads = Math.floor(((+r[ci("stored")] || 0) + (+r[ci("at posts")] || 0)) / (good === "sculpture" ? 400 : 100));
      const stock = val("stock:" + good, !!r[ci("stockpiled")]), x0 = UIX.panelX + 0x3B, hov = uiHover(x0, y, 123, 12);
      const font = hov ? 13 : stock ? 14 : 8, zid = RES[good];
      uiText(num(loads), UIX.panelX + 0x32, y, F[font]);          // "@" sign slot: one space before the digits (0x00508F00)
      uiText(zid === 16 ? str(130, 41) : str(23, zid) || good, UIX.panelX + 0x55, y, F[font]);
      UIX.hits.push([x0, y, 123, 12, () => send(`stockpile ${good} ${stock ? "off" : "on"}`, "stock:" + good, !stock), stock ? str(130, 26) : str(130, 25)]);
      // balloon (panel_click 0x00517650 page 3: hover id 1100 + row -> FUN_004F5B70): 68:168 + stockpiled, at once
      if (window.Balloon) Balloon.add(x0, y, 123, 12, stock ? 169 : 168, true);
    });
  }

  function hygiene() {                             // 0x00519A50
    const h = String(row("hygiene", "health") || ""), health = firstInt(h), target = paren(h) || health;
    text(str(56, 1), 45, 0x44, 3, 140);
    // deviation (user 10-28): the original shows only the word; ours adds the number, and the target while it
    // moves, on a line of its own (user 10-29: "Near perfect (97)" overflowed the panel)
    text(str(56, Math.min(12, Math.floor(health / 10) + 2)), 45, 0x54, health < 30 ? 4 : 3, 140);
    text(`(${health}${health !== target ? " to " + target : ""})`, 45, 0x64, health < 30 ? 4 : 3, 140);
    if (health !== target) {
      const k = health < target ? (health <= 49 ? 15 : 16) : (health <= 49 ? 13 : 14);
      text(str(56, k), 45, 0x74, health < target ? 13 : 14, 140);
    }
    sep(0x84);                                     // the original: 0x7C (ours has the number line)
    text(str(56, 17), 45, 0x8C, 13, 140);
    // city_crime_level 0x00519910 over the houses' unrest
    const u = houses().filter(b => b.occupants).map(b => (b.ov && b.ov.unrest != null) ? b.ov.unrest : (b.info && b.info.unrest) || 0);
    const n = u.length || 1, p7180 = u.filter(v => v >= 71 && v <= 80).length * 100 / n, p80 = u.filter(v => v > 80).length * 100 / n;
    let k;
    if (!u.some(v => v >= 51)) k = 23; else if (p7180 >= 51) k = 18; else if (p80 >= 26) k = 19; else if (p80 < 11) k = 22; else k = 21;
    para(str(56, k), 65, 0x9C, k === 18 || k === 19 ? 14 : 8, 100);
  }

  function administration() {                      // finance_panel_draw 0x00518420
    const TV = D.tax_levels.values, k = nearest(TV, val("tax", S.city.tax));
    const tax = v => send(`tax ${v}`, "tax", v);
    arrows(0x61, () => tax(TV[Math.max(0, k - 1)]), () => tax(TV[Math.min(TV.length - 1, k + 1)]), "taxes");
    text(str(131, 0), 55, 0x44, 13, 128);
    text(str(286, k), 55, 0x55, 13, 128);
    const hs = houses().filter(b => b.occupants), pop = hs.reduce((s, b) => s + b.occupants, 0) || 1;
    const taxed = hs.filter(b => (b.ov && b.ov.tax > 0) || (b.info && b.info.taxed));
    const scale = S.city.tax ? val("tax", S.city.tax) / S.city.tax : 1;   // a rate just picked: scale until the server has it
    const est = Math.round(scale * (12 * taxed.reduce((s, b) => s + ((b.info && b.info.tax_month) || 0), 0) || firstInt(row("administration", "taxes, last 12 months"))));
    para(`${str(60, 4)} ${est} ${str(8, 1)}`, 45, 0x7E, 13, 139);
    para(`${Math.round(100 * taxed.reduce((s, b) => s + b.occupants, 0) / pop)}% ${str(60, 5)}`, 45, 0xA2, 8, 139);
    const lost = 12 * hs.filter(b => !taxed.includes(b))       // ours: a year of what unregistered houses would pay
      .reduce((s, b) => s + Math.trunc((val("tax", S.city.tax) || 0) * b.occupants * 2 / 100 * 50 / 100), 0);
    para(`${lost} dr ${str(60, 23)}`, 45, 0xC0, 8, 139);
    sep(0xE9);
    const lm = S.city.last_month || {};
    paraLeft(`${str(60, 17)} ${Math.abs(firstInt(row("administration", "wages")) || lm.wages || 0)} dr`, 55, 0xF1, 13, 139);
    paraLeft(`${str(60, 10)} ${firstInt(row("administration", "taxes")) || lm.taxes || 0} dr`, 55, 0x104, 13, 139);
  }

  function culture() {                             // 0x00519FA0 (no Panhellenic games in the sandbox)
    const L = para(str(58, 15), 65, 0x41, 13, 100);
    sep(0x41 + 16 * L - 8);
    const hs = houses().filter(b => b.occupants), pop = hs.reduce((s, b) => s + b.occupants, 0) || 1;
    const share = k => hs.reduce((s, b) => s + ((b.coverage || {})[k] > 0 ? b.occupants : 0), 0) * 100 / pop;
    const rating = (p, y) => { const [i, f] = p < 20 ? [24, 14] : p < 40 ? [23, 14] : p < 60 ? [22, 13] : p < 80 ? [21, 13] : [20, 13]; text(str(58, i), 55, y, f); };
    [["philosophy", 16, 0x61], ["athletics", 17, 0x7B], ["drama", 18, 0x95]].forEach(([k, s, y]) => { text(str(58, s), 55, y, 13); rating(share(k), y + 12); });
    text(str(58, 19), 55, 0xAF, 13);
    const yes = S.buildings.some(b => b.key === "stadium" && b.employees > 0);
    text(str(18, yes ? 1 : 0), 55, 0xBB, yes ? 13 : 14);
  }

  function mythology() {                           // 0x0051A5D0: our sim has no gods or monsters
    text(str(59, 1), 45, 60, 13, 140);
    const GODS = ["zeus", "poseidon", "demeter", "apollo", "artemis", "ares", "aphrodite", "hermes", "athena", "hephaistos", "dionysus", "hades", "hera", "atlas"];
    S.buildings.filter(b => /^sanctuary_/.test(b.key)).slice(0, 4).forEach((b, i) => {
      const g = GODS.indexOf(b.key.replace("sanctuary_", "").replace("_grand", ""));
      text(str(157, g), 45, 72 + 24 * i, 13, 140);
      const done = b.built == null || b.built >= 100;
      text(done ? str(59, 2) : `${b.built} % ${str(59, 7)}`, 45, 84 + 24 * i, 13, 140);
    });
    sep(0xA4);
    text(str(59, 16), 45, 0xAC, 13, 140);
    text(str(58, 55), 45, 0xB8, 8, 140);
    paraLeft(str(59, 17), 55, 0xE8, 13, 150);       // text_ref_paragraph_draw: left-aligned
    text(str(58, 55), 45, 0xF4, 8, 140);
  }

  function military() {                            // 0x0051B060
    const M = window.Military && Military.data;
    if (M && M.on) return militaryLive(M);
    const t = table("military", "Companies"), icon = { horseman: 0, hoplite: 1, rabble: 2 };
    const list = [];
    for (const r of (t && t.rows) || []) for (let k = 0; k < (+r[1] || 0); k++) if (icon[r[0]] != null) list.push(icon[r[0]]);
    let y = 0x40 - 6;
    if (list.length) {
      text(str(51, 2), 0x35, y + 6, 13, 128);
      list.forEach((ic, i) => uiPut(groupSprite("Zeus_Interface", "SPR_MIL_ADVISOR_TYPES", ic), C.X + 0x35 + 24 * (i % 5), C.Y + y + 0x11 + 17 * Math.floor(i / 5)));
    }
    militaryButtons(list.length ? [8, 10] : [82, 10], () => toast(str(51, 8) + ": armies are not simulated"));
  }

  function militaryButtons(first, onFirst) {       // the three lines under the lists (widget table 0x0063ED68)
    const towers = String(row("military", "towers") || "");
    const nTowers = S.buildings.filter(b => b.key === "tower").length, manned = val("towers", !/unmanned/.test(towers));   // the row's number is the tower count, not the state
    // ships (FUN_0051AE00, sim navy.crew_all_label): 83 no ships, 5 crew all, 3 crewing all, 4 all crewed; a click
    // flips the crew-all flag (wm_sub_40A380, `navy crew`; bugs.md 329)
    const MD = window.Military && Military.data, wharves = S.buildings.some(b => b.key === "trireme_wharf");
    const crewAll = !!(MD && MD.crew_all);
    const labels = [first, [MD && MD.crew_label != null ? MD.crew_label : wharves ? 5 : 83, 10],
                    !nTowers ? [84, 10] : manned ? [11, 10] : [12, 10]];
    const clicks = [onFirst, () => wharves && sendCommands(["navy crew"]).then(() => window.Military && Military.refresh()),
                    () => nTowers && send(`towers ${manned ? "off" : "on"}`, "towers", !manned)];
    labels.forEach(([k, f], i) => {
      uiPut(groupSprite("Zeus_Interface", "SPR_MIL_ADVISOR_INFO", i), C.X + 0x35, C.Y + 0xE4 + 17 * i);
      const bx = C.X + 0x46, by = C.Y + 0xE6 + 17 * i, sp = groupSprite("Zeus_Interface", "SPR_THIN_BUTTON", 0);
      if (sp) uiPut(sp, bx, by, 1, 88, 14);
      UIX.hits.push([bx, by, 88, 14, clicks[i], typeof k === "string" ? k : str(51, k)]);
      text(typeof k === "string" ? k : str(51, k), 0x45, 0xEA + 17 * i, f, 88);
      // balloons (FUN_0051B470 hover ids 0x5DC.. -> FUN_004F5DE0, at once): soldiers 37 none / 170 all called (label
      // 51:6) / 171; ships 38 none / 173 (172 with crews out: ours has no crews); towers 39 none / 174 manned / 175
      const tip = [k === 82 ? 37 : k === 6 ? 170 : 171, labels[1][0] === 83 ? 38 : crewAll ? 172 : 173, !nTowers ? 39 : manned ? 174 : 175][i];
      if (window.Balloon && typeof k !== "string") Balloon.add(bx, by, 88, 14, tip, true);
    });
    // the fourth widget of 0x0063ED68: auto-defend helmet (86, 0) 18x28, group 0x2B1 SPR_AUTO_COMBAT_OFF / 0x2B2 _ON
    // by 0x00F2A990 (FUN_0051B060), +1 hovered (widget_table_draw); click 0x005692D0 (the Options toggle); balloon
    // 0x5DF -> 68:177 off / 176 on (FUN_004F5DE0, at once)
    const auto = !!(window.Options && Options.settings.auto_defend), hx = C.X + 0x46 + 86, hy = C.Y + 0xE6;
    const hsp = groupSprite("Zeus_Interface", auto ? "SPR_AUTO_COMBAT_ON" : "SPR_AUTO_COMBAT_OFF", uiHover(hx, hy, 18, 28) ? 1 : 0);
    if (hsp) uiPut(hsp, hx, hy);
    UIX.hits.push([hx, hy, 18, 28, () => window.Options && Options.act("0x5692d0"), "Auto defend"]);
    if (window.Balloon) Balloon.add(hx, hy, 18, 28, auto ? 176 : 177, true);
  }

  // sim/military on: the companies in three lists (FUN_0051AA40: mobilized in the city 51:0, abroad 51:1,
  // standing down 51:2), icons 24 x 17 in rows of 5 (tables 0x0063E4E0 / 0x0063E7B8 / 0x0063EA90); a click
  // selects the company (ours: its flag waves, a map click moves it; the exe opens a company panel instead)
  function militaryLive(M) {
    const icon = { horseman: 0, hoplite: 1, rabble: 2 }, comps = M.companies || [];
    const groups = [comps.filter(c => c.mob && !c.away), comps.filter(c => c.away), comps.filter(c => !c.mob && !c.away)];
    let y = groups[0].length ? 0x40 : 0x3A;       // FUN_0051B060: 0x40 under list 0, else the next title at 0x3A + 6
    groups.forEach((list, gi) => {
      if (!list.length) return;
      text(str(51, gi), 0x35, gi === 0 ? y : y + 6, 13, gi === 2 ? 0x80 : 0x8C);
      const iy = gi === 0 ? y + 0xB : y + 0x11;
      list.forEach((c, i) => {
        const x = C.X + 0x35 + 24 * (i % 5), yy = C.Y + iy + 17 * Math.floor(i / 5);
        uiPut(groupSprite("Zeus_Interface", "SPR_MIL_ADVISOR_TYPES", icon[c.type] || 0), x, yy);
        UIX.hits.push([x, yy, 24, 17, () => {          // 0x00516A50: centre on the standard, select, screen 0x48
          if (window.MilPanel) {
            MilPanel.select(c.slot);
            const p = (c.mob ? c.dest : c.home) || c.dest;
            if (p && typeof cam !== "undefined") { cam.x = tileX(p[0], p[1]) - (UIX.panelX * UIX.scale) / 2 / cam.zoom; cam.y = tileY(p[0], p[1]) - innerHeight / 2 / cam.zoom; }
          } else Military.select(Military.selected !== c.slot ? c.slot : 0);
        }, `Company ${c.slot}: ${c.type}, ${c.members} soldiers, morale ${c.morale}`]);
        const nm = typeof MAP !== "undefined" && MAP.military && MAP.military.texts && MAP.military.texts["138"];
        if (window.Balloon && nm) Balloon.addTip(x, yy, 24, 17, nm[c.banner || 0] || "");   // kind 4: 138:banner (FUN_0051C800)
      });
      y = iy + 17 * Math.ceil(list.length / 5);
    });
    const sel = Military.selected && comps.find(c => c.slot === Military.selected);
    if (sel) {                                     // ours: the selected company's orders
      const mode = ["hold", "attack", "special"][sel.mode || 0], next = ["attack", "special", "hold"][sel.mode || 0];
      const B = [[sel.mob ? "Send home" : "Mobilize", () => sendCommands([`${sel.mob ? "return" : "mobilize"} ${sel.slot}`]).then(Military.refresh)],
                 [`Stance: ${mode}`, () => sendCommands([`mode ${sel.slot} ${next}`]).then(Military.refresh)],
                 ["Rotate", () => sendCommands([`rotate ${sel.slot}`]).then(Military.refresh)]];
      B.forEach(([label, fn], i) => {
        const bx = C.X + 0x46, by = C.Y + 0xE6 + 17 * i, sp = groupSprite("Zeus_Interface", "SPR_THIN_BUTTON", 0);
        uiPut(groupSprite("Zeus_Interface", "SPR_MIL_ADVISOR_TYPES", icon[sel.type] || 0), C.X + 0x35 - 4, C.Y + 0xE4 + 17 * i);
        if (sp) uiPut(sp, bx, by, 1, 88, 14);
        UIX.hits.push([bx, by, 88, 14, fn, label]);
        text(label, 0x45, 0xEA + 17 * i, 8, 88);
      });
      return;
    }
    // FUN_0051AD60: no palace or no company 'no soldiers' (82); a company standing down whose standard is not on its
    // home building (FUN_004DD1F0; ours: status 18 'at home') 'call all' (7); else none mobilized 'at palace' (8),
    // else 'all called' (6)
    const palace = S.buildings.some(b => b.key === "palace"), out = comps.filter(c => c.mob || c.away);
    const k = !palace || !comps.length ? 82 : comps.some(c => !c.mob && !c.away && c.status !== 18) ? 7 : out.length ? 6 : 8;
    militaryButtons([k, 10], () => k !== 82 && sendCommands([k === 6 ? "return all" : "mobilize all"]).then(Military.refresh));
  }

  // 0x0051BEE0: the placed commemorative monuments (g_commemorative_placed[v], v = the building's variant) by kind,
  // 12-px rows centred in 140 from panelX+0x2B (9B): kinds 1..8 (not 4) one row each in v order, then the god
  // statues by god (FUN_0051B9D0: v 10..0x41 -> god 0..13, 157:god), then Scholar (9) and Athlete (4); a row is
  // 133:3 "[name]" (count 1) or 133:4 "[name] ([amount])" with the name of wm_sub_4663B0. Past 15 rows: Scholar +
  // Athlete become one row 133:15 (count = how many of the two kinds are placed) if that fits, else all statues one
  // row 133:14 "Gods" (their total). After the Scholar row, as the 8th row, the column moves to panelX+0xC1.
  function aesthetics() {
    para(str(133, 1), 0x2B, 0x3E, 13, 140);
    const placed = new Array(0x4B).fill(0);
    for (const b of S.buildings) if (b.key === "commemorative_monument" && b.variant >= 0 && b.variant < 0x4B) placed[b.variant]++;
    const god = (v) => {                           // FUN_0051B9D0: 4 statue sets of 12 gods, Hera and Atlas apart
      if ([0x22, 0x24, 0x3E, 0x40].includes(v)) return 12;
      if ([0x23, 0x25, 0x3F, 0x41].includes(v)) return 13;
      for (const b0 of [10, 0x16, 0x26, 0x32]) if (v >= b0 && v < b0 + 12) return v - b0;
      return -1;
    };
    const byGod = new Array(14).fill(0);
    let statues = 0, gods = 0, games = 0, other = 0;
    placed.forEach((n, v) => {
      if (!n) return;
      const g = god(v);
      if (g >= 0) { if (!byGod[g]) gods++; byGod[g] += n; statues += n; }
      else if (v === 9 || v === 4) games++;
      else other++;
    });
    if (!(games + gods + other)) { para(str(133, 2), 0x2B, 0x60, 14, 140); return; }
    let a1 = false, a2 = false;                    // DAT_00FA04A1 (gods merged), DAT_00FA04A2 (games merged)
    if (games + gods + other >= 16) {
      if (gods + 1 + other < 16) a2 = true;
      else if (games + 1 + other < 16) a1 = true;
    }
    const KIND = { 1: 5, 2: 7, 3: 10, 5: 8, 6: 11, 7: 6, 8: 9, 9: 12, 4: 13 };   // wm_sub_4663B0: v -> 133:k
    let x = 0x2B, y = 0x60, rows = 0;
    const row = (name, n) => {
      if (!n) return false;
      text(n === 1 ? name : `${name} (${n})`, x, y, 8, 140);        // 133:3 / 133:4
      rows++; y += 12;
      return true;
    };
    for (let v = 0; v < 0x4B; v++) if (god(v) < 0 && v !== 4 && v !== 9) row(KIND[v] ? str(133, KIND[v]) : "", placed[v]);
    if (!a1) byGod.forEach((n, g) => row(str(157, g), n));
    else row(str(133, 14), statues);
    if (!a2) {
      if (row(str(133, 12), placed[9]) && rows === 8) { x = 0xB7; y = 0x60; }
      row(str(133, 13), placed[4]);
    } else row(str(133, 15), games);
  }

  function overview() {                            // 0x005B6F00: city update rows (15 px), values right-aligned
    const B = 0x3C, c = S.city, right = (s, y, f, w = 120) => uiText(s, C.X + 0x37, C.Y + y, F[f], { align: "right", width: w });
    const lab = (k, y) => text(str(61, k), 0x37, y, 13);
    const sent = c.sentiment || 0, pi = sent < 1 ? 27 : sent >= 100 ? 38 : 27 + Math.floor(sent / 10) + 1;
    lab(1, B); right(str(61, pi), B, sent < 30 ? 14 : 8);
    const stored = firstInt(row("husbandry", "food stored")), eaten = firstInt(row("husbandry", "eaten per month"));
    const fp = eaten ? Math.floor(stored * 100 / eaten) : 0, [fk, ff] = fp <= 0 ? [94, 14] : fp < 50 ? [95, 14] : fp < 100 ? [96, 8] : [97, 8];
    lab(4, B + 0xF); right(str(61, fk), B + 0xF, ff);
    const wf = c.workforce || 0, up = wf ? Math.round(100 * (c.unemployed || 0) / wf) : 0, jobs = firstInt(row("industry", "jobs open"));
    if (up < 6 && jobs < 6) text(str(61, 115), 0x37, B + 0x1E, 13);
    else if (up >= 1) { const f = up >= 11 ? 14 : 8; text(str(61, up >= 11 ? 107 : up >= 6 ? 109 : 110), 0x37, B + 0x1E, f); right(`@${up}%`, B + 0x1E, f, 115); }
    else { const f = jobs >= 11 ? 14 : 8; text(str(61, jobs >= 21 ? 111 : jobs >= 11 ? 112 : 113), 0x37, B + 0x1E, f); uiText(`@${jobs}`, C.X + 0x30, C.Y + B + 0x1E, F[f], { align: "right", width: 120 }); }
    const health = firstInt(row("hygiene", "health"));
    lab(6, B + 0x2D); right(str(61, 127 + Math.min(10, Math.floor(health / 10))), B + 0x2D, health < 30 ? 14 : 8);
    const u = houses().filter(b => b.occupants).map(b => (b.ov && b.ov.unrest != null) ? b.ov.unrest : (b.info && b.info.unrest) || 0);
    const p81 = u.length ? u.filter(v => v >= 81).length * 100 / u.length : 0;
    const uk = !u.some(v => v > 0) ? 149 : p81 > 50 ? 144 : p81 >= 26 ? 145 : p81 >= 11 ? 146 : 148;
    lab(7, B + 0x3C); right(str(61, uk), B + 0x3C, uk <= 146 ? 14 : 8);
    const fin = firstInt(row("administration", "taxes - wages, last 12 months")), [nk, nf] = fin > 0 ? [153, 8] : fin < 0 ? [155, 14] : [154, 8];
    lab(8, B + 0x4B); right(str(61, nk), B + 0x4B, nf);
    text(str(61, 190), 0x37, B + 0x5A, 8);
    sep(B + 0x69);
    text(str(61, 195), 0x37, B + 0x70, 3, 130);
    // request rows (0x005B6F00, the list of request_list_rebuild 0x00483040, S.requests): the first 3, 0x14 apart,
    // pictures at B + 0x7F, text at B + 0x83; past 3 the 'more' line 61:0xC4 centred, 5 px over the next row
    const rq = (S && S.requests) || [], IR = (k) => groupSprite("Zeus_Interface", k ? "SPR_REQUEST_COMPLETE" : "SPR_REQUEST_INCOMPLETE");
    rq.slice(0, 3).forEach((q, k) => {
      const iy = C.Y + B + 0x7F + 0x14 * k, ty = B + 0x83 + 0x14 * k;
      if (q.kind === "quest") {                    // FUN_005BDDD0: the hero in the city and free -> bullet 12, font 13
        uiPut(IR(q.ready), C.X + 0x37, iy);
        if (q.god < 12) uiPut(groupSprite("Zeus_General", "SPR_GOD_QUEST_ICON", q.god), C.X + 0x47, iy);
        text(str(157, q.god), 0x61, ty, q.ready ? 13 : 8);
        return;
      }
      uiPut(IR(q.can), C.X + 0x37, iy);            // FUN_004713E0 (the stock covers it): bullet 12, font 13
      const ic = window.Advisors && Advisors.requestIcon(q.item);
      if (ic) uiPut(ic, C.X + 0x47, iy);
      const f = q.can ? 13 : q.relation === "ally" ? 14 : 8;
      text(q.city, 0x61, ty, f);
      if (q.overdue) text(str(61, 0xCE), 0x8B, ty, 14);
      else {
        text(window.ZText ? ZText.numberText(q.months, "@", "") : String(q.months), 0x8B, ty, f);
        uiPut(groupSprite("Zeus_Interface", "SPR_MOON"), C.X + 0x9F, iy);
      }
    });
    if (rq.length > 3) text(str(61, 0xC4), 0x37, B + 0x7F + 0x14 * 3 - 5, 14, 0x82);
  }

  const PAGES = [population, husbandry, industry, distribution, hygiene, administration, culture, mythology, military, aesthetics, overview];

  function draw(page, X, nOverlays) {
    if (!D || !S || !S.city) return;
    C = { X, Y: nOverlays * 20 };
    const fn = PAGES[page] || (window.ZPagesExtra && ZPagesExtra[page]);
    if (fn) fn({ text, para, sep, str, num, row, table, firstInt, paren, houses, send, F, C });
  }
  return { draw, row, table };
})();
window.ZPages = ZPages;
